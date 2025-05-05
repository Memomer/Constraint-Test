import autogen
import yaml
from datetime import datetime

# Configuration for the LLM
config_list = [
    {
        "model": "gpt-4o-mini",  # Using the mini model as requested
        "api_key": "YOUR_API_KEY",
    }
]

llm_config = {
    "config_list": config_list,
    "seed": 42,  # For reproducibility
    "temperature": 0.7,
}

rule = """You are only allowed to talk using 1 letter from alphabet series and send letter
          as a response to another agent, you are not allowed to give any explanations as to
          why you chose the word unless prompted to till then limit your responses to only 1 letter"""

def get_agent_reasoning(agent, chat_history):
    """Get the reasoning behind an agent's letter choices"""
    reasoning_prompt = f"""Please explain your reasoning behind each letter choice in the following conversation:
    {chat_history}
    For each letter you chose, explain:
    1. Why you chose that specific letter
    2. What you were trying to communicate
    3. Any patterns or strategies you developed
    Please be detailed in your explanation."""
    
    return agent.generate_reply(
        messages=[{"role": "user", "content": reasoning_prompt}],
        sender=user_proxy
    )

def generate_yaml_file(agentSHV_reasoning, agentVSH_reasoning, chat_history):
    """Generate YAML file with reasoning and empty observations"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # First, try to read existing YAML file
    try:
        with open("agent_interactions.yaml", "r") as f:
            existing_data = yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError):
        existing_data = {"message_history": {"rules": []}}
    
    # Create new rule entry
    new_rule = {
        "rule_id": f"RULE_{len(existing_data['message_history']['rules']) + 1:03d}",
        "timestamp": current_time,
        "message": rule,
        "implemented_by": "AgentSHV and AgentVSH",
        "status": "active",
        "observations": [{
            "observation_id": f"OBS_{len(existing_data['message_history']['rules']) + 1:03d}_001",
            "timestamp": current_time,
            "message": "",
            "iterations": "",
            "context": "Initial interaction phase",
            "significance": "High"
        }]
    }
    
    # Append new rule to existing rules
    existing_data['message_history']['rules'].append(new_rule)
    
    # Write back to YAML file
    with open("agent_interactions.yaml", "w") as f:
        yaml.dump(existing_data, f, default_flow_style=False)

# Create the two assistant agents
agentSHV = autogen.AssistantAgent(
    name="AgentSHV",
    llm_config=llm_config,
    system_message=f"You are Agent1. You are having a conversation with Agent2. {rule}",
    description="An experimental agent."
)

agentVSH = autogen.AssistantAgent(
    name="AgentVSH",
    llm_config=llm_config,
    system_message=f"You are AgentVSH. You are having a conversation with AgentSHV. {rule}",
    description="An experimental agent."
)

# Create the user proxy agent
user_proxy = autogen.UserProxyAgent(
    name="User",
    human_input_mode="ALWAYS",  # This ensures user can interject at any time
    max_consecutive_auto_reply=10,
    is_termination_msg=lambda x: x.get("content", "").lower().endswith("terminate"),
    llm_config=llm_config,
    code_execution_config={
        "work_dir": "coding",
        "use_docker": False
    },
)

# Create a group chat for agents only
agent_chat = autogen.GroupChat(
    agents=[agentSHV, agentVSH, user_proxy],  # Added user_proxy to the group
    speaker_selection_method="round_robin",
    messages=[],
    max_round=20,
)

# Create the manager for agent conversation
agent_manager = autogen.GroupChatManager(
    groupchat=agent_chat,
    llm_config=llm_config,
    is_termination_msg=lambda x: x.get("content", "").lower().endswith("explain_reasoning"),
)

# Start the agent conversation
print("Starting conversation between Agent1 and Agent2...")
print("You can interject at any time by typing your message.")
print("Type 'explain_reasoning' to get agents' reasoning.")
print("Type 'terminate' to end the conversation.\n")

agentSHV.initiate_chat(
    agent_manager,
    message=f"We are testing emergent Rule Test : {rule}",
    description=f"{rule}"
)

# Main interaction loop
while True:
    user_input = input("User: ")
    
    if user_input.lower() == "terminate":
        # Trigger final reasoning collection
        agentSHV.send(
            message="explain_reasoning",
            recipient=agent_manager,
        )
        
        # Get final reasoning
        final_chat_history = agent_chat.messages
        final_agentSHV_reasoning = get_agent_reasoning(agentSHV, final_chat_history)
        final_agentVSH_reasoning = get_agent_reasoning(agentVSH, final_chat_history)
        
        # Generate YAML file with reasoning
        generate_yaml_file(final_agentSHV_reasoning, final_agentVSH_reasoning, final_chat_history)
        print("\nYAML file generated with reasoning and empty observations.")
        break
    
    # Send the user's message to the group chat
    user_proxy.send(
        message=user_input,
        recipient=agent_manager,
    )
