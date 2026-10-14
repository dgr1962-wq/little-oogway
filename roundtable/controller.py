import yaml
import time
from utils.logger import log
from agents.ai_handlers import launch_agent

CONFIG_PATH = "config/agents.yaml"

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def main():
    log("🎛️  Roundtable Controller initialized.")
    config = load_config()

    # Launch agents
    agents = config.get("agents", {})
    for name, settings in agents.items():
        log(f"🔹 Summoning {name}...")
        launch_agent(name, settings)

    # Command loop
    while True:
        cmd = input("\n🔧 Command > ").strip().lower()
        if cmd in ("exit", "quit", "q"):
            log("🛑 Shutting down Roundtable...")
            break
        elif cmd == "list":
            print("👥 Active agents:", ", ".join(agents.keys()))
        else:
            log(f"⚠️ Unknown command: {cmd}")

if __name__ == "__main__":
    main()
