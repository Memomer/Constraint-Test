import autogen
from dataclasses import dataclass
from typing import Optional, List, Dict
from autogen.agentchat.groupchat import GroupChat
from autogen.formatting_utils import colored
from autogen.io.base import IOStream

# Global variable for the reasoning prompt
REASONING_PROMPT = "explain your reasoning for the letters you have chosen so far."

@dataclass
class SmartGroupChat(GroupChat):
    """A smart group chat class that extends GroupChat to automatically trigger
    reasoning explanations based on a provided trigger round.
    """
    trigger_reasoning_round: Optional[int] = None  # Add trigger_reasoning_round as an attribute

    def trigger_reasoning(self):
        """Prompts all agents to explain their reasoning using the global prompt."""
        print(colored(f"\n--- Round {self.round_count}: Triggering Automatic Reasoning ---\n", "magenta"))
        for agent in self.agents:
            agent.send(REASONING_PROMPT, self, request_reply=False)
            reply = agent.generate_reply(self.messages)
            if reply:
                self.append(reply, agent)
                print(colored(f"{agent.name}: {content_str(reply['content'])}\n", "cyan"))
        print(colored("--- End of Automatic Reasoning ---\n", "magenta"))

    def run_round(
        self,
        speaker: autogen.Agent,
        message: Optional[str] = None,
        messages: Optional[List[Dict]] = None,
    ) -> Optional[autogen.Agent]:
        """Run one round of the group chat with an optional reasoning trigger."""
        super().run_round(speaker, message, messages)  # Call the parent's run_round

        if self.trigger_reasoning_round is not None and self.round_count == self.trigger_reasoning_round:
            self.trigger_reasoning()

        return self.next_agent(speaker)

    def run(self, messages: Optional[List[Dict]] = None, speaker: Optional[autogen.Agent] = None, max_rounds: Optional[int] = None) -> Optional[List[Dict]]:
        """Run the smart group chat with an option to trigger reasoning at a specific round."""
        if messages is not None:
            self.messages = messages
        if speaker is None:
            speaker = self.agents[0]
        if max_rounds is None:
            max_rounds = self.max_round

        if self.send_introductions and not any(
            msg["role"] == "system" and msg["content"].startswith(self.DEFAULT_INTRO_MSG)
            for msg in self.messages
        ):
            self.messages.insert(0, {"role": "system", "content": self.introductions_msg()})

        self.round_count = 0  # Initialize round counter for the smart chat
        while self.round_count < max_rounds:
            try:
                # Get the next speaker
                next_speaker, eligible_agents, select_speaker_messages = self._prepare_and_select_agents(speaker)
                if next_speaker is None:
                    break  # No speaker selected, terminate the loop

                speaker = next_speaker
                if self.logging_enabled():
                    self.logger.info(f"Next speaker: {speaker.name}")

                # Run one round (which now includes the optional reasoning trigger)
                next_speaker = self.run_round(speaker)
                if next_speaker is None:
                    break  # No reply generated, terminate the loop

                self.round_count += 1
            except KeyboardInterrupt:
                # Let the admin agent take over
                admin = self.agent_by_name(self.admin_name)
                if admin is not None:
                    speaker = admin
                    message = IOStream.get_default().input(f"{speaker.name} taking over (Ctrl+C again to end): ")
                    if message == "exit":
                        break
                    self.run_round(speaker, message)
                    self.round_count += 1  # Increment round count even for admin takeover
        return self.messages