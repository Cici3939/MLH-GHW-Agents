import json
import os
import re
import textwrap
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, Response, jsonify, render_template, request, stream_with_context


BASE_DIR = Path(__file__).resolve().parent
DEBATES_DIR = BASE_DIR / "debates"
DEBATES_DIR.mkdir(exist_ok=True)

OPENAI_MODEL = "gpt-5.3-chat-latest"
ANTHROPIC_MODEL = "claude-opus-5"
JUDGE_MODEL = os.getenv("JUDGE_MODEL", OPENAI_MODEL)

app = Flask(__name__)


# Common U.S. debate structure: Pro/Affirmative opens, Con/Negative answers,
# both sides clash with evidence, then closing statements and a judge ballot.
DEBATE_FORMAT = [
    {
        "phase": "Pro Constructive",
        "speaker": "Pro Agent",
        "side": "pro",
        "instruction": "Start the debate by supporting the question. Give an evidence-focused opening case with a clear claim, warrants, and impacts.",
    },
    {
        "phase": "Con Constructive",
        "speaker": "Con Agent",
        "side": "con",
        "instruction": "Argue against the question. Take Pro's argument into account, then give evidence-focused counterclaims, warrants, and impacts.",
    },
    {
        "phase": "Pro Evidence Rebuttal",
        "speaker": "Pro Agent",
        "side": "pro",
        "instruction": "Respond below Con's argument by weighing evidence, answering Con's strongest objections, and rebuilding Pro's case.",
    },
    {
        "phase": "Con Evidence Rebuttal",
        "speaker": "Con Agent",
        "side": "con",
        "instruction": "Answer Pro's latest evidence comparison, extend Con's best evidence, and explain why Con's impacts outweigh.",
    },
    {
        "phase": "Pro Cross-Examination",
        "speaker": "Pro Agent",
        "side": "pro",
        "instruction": "Ask pointed evidence-testing questions about Con's assumptions, then explain what those questions reveal.",
    },
    {
        "phase": "Con Cross-Examination",
        "speaker": "Con Agent",
        "side": "con",
        "instruction": "Ask pointed evidence-testing questions about Pro's assumptions, then explain what those questions reveal.",
    },
    {
        "phase": "Pro Closing Statement",
        "speaker": "Pro Agent",
        "side": "pro",
        "instruction": "Crystallize the evidence, compare impacts, and explain why the Judge should vote Pro.",
    },
    {
        "phase": "Con Closing Statement",
        "speaker": "Con Agent",
        "side": "con",
        "instruction": "Crystallize the evidence, compare impacts, and explain why the Judge should vote Con.",
    },
]


def post_json(url, headers, payload, timeout=75):
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def call_openai(messages, model=OPENAI_MODEL):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        result = post_json(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            {"model": model, "messages": messages, "temperature": 0.72, "max_tokens": 800},
        )
        return result["choices"][0]["message"]["content"].strip()
    except (HTTPError, URLError, KeyError, TimeoutError, json.JSONDecodeError) as exc:
        return f"[OpenAI call unavailable: {exc}]"


def call_anthropic(system_prompt, user_prompt, model=ANTHROPIC_MODEL):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        result = post_json(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "max_tokens": 800,
                "temperature": 0.72,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        return "\n".join(part.get("text", "") for part in result.get("content", [])).strip()
    except (HTTPError, URLError, KeyError, TimeoutError, json.JSONDecodeError) as exc:
        return f"[Anthropic call unavailable: {exc}]"


def fallback_agent_response(question, side, phase):
    stance = "supports" if side == "pro" else "opposes"
    opponent = "Con" if side == "pro" else "Pro"
    return textwrap.dedent(
        f"""
        In this {phase}, the {side.title()} position {stance} the resolution: “{question}”.

        Evidence lens: voters should prefer the side that gives the most probable real-world impacts, explains the mechanism behind those impacts, and answers the other side's strongest warrant. The available public record on most policy and social questions rewards careful tradeoff analysis over slogans.

        {opponent}'s position leaves key assumptions under-tested. The {side.title()} side gives the clearer decision rule, weighs consequences more directly, and better explains why its evidence should control the ballot.
        """
    ).strip()


def transcript_context(transcript):
    if not transcript:
        return "No prior speeches yet."
    return "\n\n".join(f"[{item['phase']}] {item['speaker']}:\n{item['text']}" for item in transcript)


def generate_agent_turn(question, turn, transcript):
    shared_rules = textwrap.dedent(
        """
        You are participating in a formal United States-style educational debate.
        Use the common debate rhythm: Pro/Affirmative opens, Con/Negative answers, both sides clash through evidence rebuttal and cross-examination, then closing statements crystallize voting issues.
        Argue mainly from evidence: name the type of evidence you rely on, explain its warrant, compare it against the opponent's evidence, and do not invent fake citations or exact statistics.
        Be civil, direct, and persuasive. Keep the speech under 220 words.
        """
    ).strip()
    prompt = textwrap.dedent(
        f"""
        Debate resolution/question: {question}

        Current phase: {turn['phase']}
        Your role: {turn['speaker']} ({turn['side'].upper()})
        Task: {turn['instruction']}

        Prior transcript:
        {transcript_context(transcript)}
        """
    ).strip()

    if turn["side"] == "pro":
        response = call_openai(
            [
                {"role": "system", "content": shared_rules + " You are the Pro Agent. Argue to support the user's question."},
                {"role": "user", "content": prompt},
            ]
        )
    else:
        response = call_anthropic(shared_rules + " You are the Con Agent. Argue against the user's question while accounting for Pro's prior speech.", prompt)

    return response or fallback_agent_response(question, turn["side"], turn["phase"])


def generate_judgment(question, transcript):
    prompt = textwrap.dedent(
        f"""
        You are the Judge Agent for a formal U.S.-style debate. Decide the winner using normal judge criteria:
        clash, responsiveness, burden of proof, evidence quality, warrant comparison, impact weighing, and final crystallization.

        Debate resolution/question: {question}

        Full transcript:
        {transcript_context(transcript)}

        Write 2-4 concise paragraphs of reasoning. Explicitly compare the quality of evidence and responsiveness.
        End with exactly one final line:
        Winner: Pro
        or
        Winner: Con
        or
        Winner: Tie
        """
    ).strip()
    response = call_openai(
        [
            {"role": "system", "content": "You are a fair, concise debate judge. Do not default to either side."},
            {"role": "user", "content": prompt},
        ],
        model=JUDGE_MODEL,
    )
    if response:
        return response

    return textwrap.dedent(
        """
        Both sides followed the core burdens of a U.S.-style debate: Pro opened the affirmative case, Con answered it, both sides rebuilt through rebuttal, and each side crystallized the round. The most important voting issue is evidence comparison, not which side sounded more confident.

        Pro did a better job connecting its evidence claims to a clear mechanism and final impact. Con raised relevant risks, but Pro's rebuttal more directly answered those risks and explained why its impacts were more probable.

        Winner: Pro
        """
    ).strip()


def split_winner_line(judgment):
    match = re.search(r"(?:^|\n)\s*Winner:\s*(Pro|Con|Tie)\s*$", judgment, re.IGNORECASE)
    if not match:
        return judgment.strip(), "Tie", "Winner: Tie"
    winner = match.group(1).title()
    reasoning = judgment[: match.start()].strip()
    return reasoning, winner, f"Winner: {winner}"


def safe_slug(question):
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")
    return slug[:72].strip("-") or "debate"


def save_markdown(question, transcript, judgment, winner):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{safe_slug(question)}-{timestamp}.md"
    path = DEBATES_DIR / filename
    lines = [
        f"# Cat Galaxy Debate: {question}",
        "",
        f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Winner: {winner}",
        f"- Pro Agent Model: {OPENAI_MODEL}",
        f"- Con Agent Model: {ANTHROPIC_MODEL}",
        f"- Judge Agent Model: {JUDGE_MODEL}",
        "- Debate Style: U.S.-style evidence-based constructive, clash, rebuttal, closing, and judge ballot",
        "",
        "## Transcript",
        "",
    ]
    for item in transcript:
        lines.extend([f"### {item['phase']} — {item['speaker']}", "", item["text"], ""])
    lines.extend(["## Judge Decision", "", judgment, ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return filename


def stream_event(event, payload):
    return json.dumps({"event": event, **payload}) + "\n"


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/debate/stream")
def stream_debate():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Please enter a debate question."}), 400
    if len(question) > 500:
        return jsonify({"error": "Please keep the debate question under 500 characters."}), 400

    @stream_with_context
    def generate():
        transcript = []
        yield stream_event("meta", {"question": question, "format": "Pro opens, Con answers, evidence rebuttals, cross-examination, closings, judge ballot."})

        for index, turn in enumerate(DEBATE_FORMAT):
            yield stream_event("turn_start", {"turn": {**turn, "index": index}})
            text = generate_agent_turn(question, turn, transcript)
            transcript.append({**turn, "text": text})
            yield stream_event("turn_text", {"turn": {**turn, "index": index, "text": text}})

        judge_turn = {"phase": "Judge Decision", "speaker": "Judge Agent", "side": "judge", "index": len(DEBATE_FORMAT)}
        yield stream_event("turn_start", {"turn": judge_turn})
        judgment = generate_judgment(question, transcript)
        reasoning, winner, winner_line = split_winner_line(judgment)
        full_judgment = f"{reasoning}\n\n{winner_line}" if reasoning else winner_line
        yield stream_event("judge_reasoning", {"turn": {**judge_turn, "text": reasoning}})
        yield stream_event("suspense", {"message": "The cosmic cat Judge is batting the ballot around..."})
        time.sleep(1.5)
        yield stream_event("winner", {"winner": winner, "winner_line": winner_line})
        filename = save_markdown(question, transcript, full_judgment, winner)
        yield stream_event(
            "saved",
            {
                "markdown_file": filename,
                "saved_message": "Your debate has been saved to a tab in this website called “Past Debates”.",
            },
        )
        yield stream_event("done", {})

    return Response(generate(), mimetype="application/x-ndjson")


@app.post("/api/debate")
def create_debate():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Please enter a debate question."}), 400
    if len(question) > 500:
        return jsonify({"error": "Please keep the debate question under 500 characters."}), 400

    transcript = []
    for turn in DEBATE_FORMAT:
        text = generate_agent_turn(question, turn, transcript)
        transcript.append({**turn, "text": text})
    judgment = generate_judgment(question, transcript)
    reasoning, winner, winner_line = split_winner_line(judgment)
    full_judgment = f"{reasoning}\n\n{winner_line}" if reasoning else winner_line
    filename = save_markdown(question, transcript, full_judgment, winner)
    return jsonify(
        {
            "question": question,
            "transcript": transcript + [{"phase": "Judge Decision", "speaker": "Judge Agent", "side": "judge", "text": full_judgment}],
            "winner": winner,
            "markdown_file": filename,
            "saved_message": "Your debate has been saved to a tab in this website called “Past Debates”.",
        }
    )


@app.get("/api/debates")
def list_debates():
    files = sorted(DEBATES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonify([
        {"filename": path.name, "title": path.stem, "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")}
        for path in files
    ])


@app.get("/api/debates/<path:filename>")
def get_debate(filename):
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        return jsonify({"error": "Invalid debate filename."}), 400
    path = DEBATES_DIR / filename
    if not path.exists():
        return jsonify({"error": "Debate not found."}), 404
    return jsonify({"filename": path.name, "content": path.read_text(encoding="utf-8")})


if __name__ == "__main__":
    app.run(debug=True, threaded=True)
