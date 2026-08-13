# MLH-GHW-Agents

Created using Backboard.io for the MLH Gloabl Hack Week: Agents. Wasn't able to finish due to tokens running out.

https://github.com/user-attachments/assets/0b9d5dfa-1e57-4aa9-8d97-4ed51201c997

Prompt: Build a cat-themed website using CSS/HTML/Javascript and Python with Flash on the backend. Make it clean, modern, dark mode with a galaxy accent. 

Build 3 agents: the Pro agent, the Con agent, and the Judge agent.

Use the Backboard API
(docs at https://docs.backboard.io). Requirements:

1. Use the official backboard-sdk pip package.
2. Read my API key from the BACKBOARD_API_KEY environment variable. Never
   hardcode it.

On the website should have a input box where the user can enter any question. Then below that input box there should be a digital debate arena where the pro agent and the con agent should debate against each other. Build the Pro agent using gpt-5.3-chat-latest from Backboard and the Con agent using claude-opus-5 from Backboard. The pro agent should have chatbox on the left side and the con agent should have chatbox on the right side. The user should be able to see the agents debating in real time. Pro goes first, then Con. do it chatting style. At the end of the debate, the Judge agent should declare a winner with reasoning. The user should be able to see the Judge agent typing in real time. The judge agent should have a chatbox in the middle of the debate arena. The debate arena should be scrollable and each chatbox should have different colors (Pro agent’s color is different from Con agent’s color which is different from the Judge agent’s color which is different from the initial input box color). At the end of the judge agent’s reasoning, it should delay a little bit for suspense and then declare a winner and make a pop up celebration window to display the winning side in all its glory. There should be a button at the end to restart the debate and make the user input another debate question AND a text saying your debate has been saved to a tab in this website called “Past Debates”. save the debate session as a markdown file in the website. Name the markdown file appropriately according to the initial debate question. The website should have another tab for the user to view each markdown files.

Pro should start the debate, arguing to support the question. Then after Pro, Con starts arguing against the question, taking Pro’s argument into account. Con’s chatbox should be below Pro’s chatbox and to the right of the arena. Then Pro should start below Con’s chatbox and to the left, arguing based on evidence and Con’s previous argument. They should mainly argue using evidence from the real world instead of solely criticizing the other side. They should actually state why they support or not support the question. The chatbox should stretch based on the length of the output text each agent delivers. Make it more conversational by saying things like “I think” or “this proves my point” or “Con is wrong because.” Make them talk like actual debater humans. The agents should send messages with web_search="Auto" so they can search the web and find real evidence from the web related to the questions and not the method of debate and tell them to the user and the judge. They should say what evidence they considered instead of just saying “the evidence that is the best is___”. The judge should be analyzing only the texts the Pro and Con agents output when deciding the winner. The Pro should be able to read and extract Con’s evidence to rebut it and vice versa.
