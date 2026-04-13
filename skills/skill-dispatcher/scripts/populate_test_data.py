import json
from pathlib import Path
from datetime import datetime
import random

log_path = Path(r"c:\projects\skills\skill-dispatcher\skills\skill-dispatcher\logs\dispatch_events.jsonl")
log_path.parent.mkdir(parents=True, exist_ok=True)

# Generate 40 skills with varying counts
skills_list = [f"Skill-{i:02d}" for i in range(1, 41)]
test_data = []

for skill in skills_list:
    count = random.randint(1, 10)
    for _ in range(count):
        test_data.append((skill, f"Intent for {skill}", f"Reason for {skill}"))

# Shuffle to simulate random arrivals
random.shuffle(test_data)

with open(log_path, "w", encoding="utf-8") as f:
    for skill, intent, reason in test_data:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "selected_skill": skill,
            "intent": intent,
            "reason": reason
        }
        f.write(json.dumps(entry) + "\n")

print(f"Populated {log_path} with {len(test_data)} events for 40 skills.")
