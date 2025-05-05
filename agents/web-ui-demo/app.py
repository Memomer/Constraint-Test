from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import autogen
import yaml
from datetime import datetime
import threading
import queue

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# Message queue for communication between the agent thread and Flask
message_queue = queue.Queue()

# Configuration for the LLM
config_list = [
    {
        "model": "gpt-4o-mini",
        "api_key": "YOUR_API_KEY",
    }
]

llm_config = {
    "config_list": config_list,
    "seed": 42,
    "temperature": 0.7,
}

# Core rule definition
CORE_RULE = "You are only allowed to talk using 1 letter from alphabet series and send letter as a response to another agent"

# Additional constraints and conditions
RULE_CONSTRAINTS = [
    "You are not allowed to give any explanations unless user inputs 'explain_reasoning'",
    "Follow the core rule strictly in all interactions"
]

# Combine rules into a single string for agent use
rule = f"{CORE_RULE}. {' '.join(RULE_CONSTRAINTS)}"

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
    
    try:
        with open("agent_interactions.yaml", "r") as f:
            existing_data = yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError):
        existing_data = {"message_history": {"rules": []}}
    
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
    
    existing_data['message_history']['rules'].append(new_rule)
    
    with open("agent_interactions.yaml", "w") as f:
        yaml.dump(existing_data, f, default_flow_style=False)

class CustomUserProxyAgent(autogen.UserProxyAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message_queue = message_queue

    def generate_reply(self, *args, **kwargs):
        reply = super().generate_reply(*args, **kwargs)
        if reply:
            self.message_queue.put({
                "role": self.name,
                "content": reply
            })
        return reply

# Create the agents
agentSHV = autogen.AssistantAgent(
    name="AgentSHV",
    llm_config=llm_config,
    system_message=f"You are Agent1. You are having a conversation with Agent2. {rule}",
)

agentVSH = autogen.AssistantAgent(
    name="AgentVSH",
    llm_config=llm_config,
    system_message=f"You are AgentVSH. You are having a conversation with AgentSHV. {rule}",
)

user_proxy = CustomUserProxyAgent(
    name="User",
    human_input_mode="NEVER",  # Changed to NEVER since we'll handle input through the web interface
    max_consecutive_auto_reply=10,
    is_termination_msg=lambda x: x.get("content", "").lower().endswith("terminate"),
    llm_config=llm_config,
    code_execution_config={
        "work_dir": "coding",
        "use_docker": False
    },
)

# Create the group chat
agent_chat = autogen.GroupChat(
    agents=[agentSHV, agentVSH, user_proxy],
    speaker_selection_method="round_robin",
    messages=[],
    max_round=20,
)

# Create the manager
agent_manager = autogen.GroupChatManager(
    groupchat=agent_chat,
    llm_config=llm_config,
    is_termination_msg=lambda x: x.get("content", "").lower().endswith("explain_reasoning"),
)

def run_agent_conversation():
    """Run the agent conversation in a separate thread"""
    agentSHV.initiate_chat(
        agent_manager,
        message=f"Rule in Action: {rule}",
        description=f"{rule}"
    )

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    # Start the agent conversation in a separate thread
    thread = threading.Thread(target=run_agent_conversation)
    thread.daemon = True
    thread.start()

@socketio.on('user_message')
def handle_user_message(data):
    message = data.get('message', '')
    if message.lower() == 'terminate':
        # Handle termination
        agentSHV.send(
            message="explain_reasoning",
            recipient=agent_manager,
        )
        final_chat_history = agent_chat.messages
        final_agentSHV_reasoning = get_agent_reasoning(agentSHV, final_chat_history)
        final_agentVSH_reasoning = get_agent_reasoning(agentVSH, final_chat_history)
        generate_yaml_file(final_agentSHV_reasoning, final_agentVSH_reasoning, final_chat_history)
        emit('system_message', {'content': 'Conversation terminated. YAML file generated.'})
    else:
        # Send user message to the agent manager
        user_proxy.send(
            message=message,
            recipient=agent_manager,
        )

def check_message_queue():
    """Check for new messages and emit them to connected clients"""
    while True:
        try:
            message = message_queue.get_nowait()
            socketio.emit('agent_message', message)
        except queue.Empty:
            break

@socketio.on('disconnect')
def handle_disconnect():
    pass

if __name__ == '__main__':
    socketio.start_background_task(check_message_queue)
    socketio.run(app, debug=True) 
