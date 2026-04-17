#!/usr/bin/env python3
"""Portfolio Push Sync - Identifies skill repos with unsaved changes and pushes them.
Only targets folders with an active Git remote.
"""

import os
import subprocess
from pathlib import Path

def run_git(cmd, cwd):
    try:
        result = subprocess.run(
            ["git"] + cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )
        return result
    except Exception as e:
        print(f" [!] System error in {cwd.name}: {e}")
        return None

def sync_portfolio(root_dir):
    root_dir = Path(root_dir).resolve()
    print(f"[*] Starting Git sweep in {root_dir}...")
    
    synced = []
    errors = []
    skipped = []

    for skill_dir in root_dir.iterdir():
        if not skill_dir.is_dir():
            continue
            
        # 1. Check for Git Repository
        dot_git = skill_dir / ".git"
        if not dot_git.exists():
            skipped.append(f"{skill_dir.name} (Not a git repo)")
            continue
            
        # 2. Check for Remote
        remote_check = run_git(["remote", "-v"], skill_dir)
        if not remote_check or not remote_check.stdout.strip():
            skipped.append(f"{skill_dir.name} (No remote found)")
            continue
            
        # 3. Check for Changes
        status = run_git(["status", "--porcelain"], skill_dir)
        if not status or not status.stdout.strip():
            # Check for unpushed commits (branch is ahead)
            ahead_check = run_git(["rev-list", "HEAD...@{u}"], skill_dir)
            if not ahead_check or not ahead_check.stdout.strip():
                skipped.append(f"{skill_dir.name} (Clean and up-to-date)")
                continue
            else:
                print(f"[*] {skill_dir.name}: Ahead of remote. Pushing...")
                push_res = run_git(["push"], skill_dir)
                if push_res.returncode == 0:
                    synced.append(f"{skill_dir.name} (Pushed existing commits)")
                    continue
                else:
                    errors.append(f"{skill_dir.name} (Push failed)")
                    continue

        # 4. Commit and Push Changes
        print(f"[+] {skill_dir.name}: Found uncommitted changes. Syncing...")
        
        run_git(["add", "."], skill_dir)
        commit_res = run_git(["commit", "-m", "chore: sync metadata and telemetry standards"], skill_dir)
        
        if commit_res.returncode == 0:
            push_res = run_git(["push"], skill_dir)
            if push_res.returncode == 0:
                synced.append(f"{skill_dir.name} (Committed and Pushed)")
            else:
                errors.append(f"{skill_dir.name} (Push failed after commit)")
        else:
            errors.append(f"{skill_dir.name} (Commit failed)")

    return synced, skipped, errors

if __name__ == "__main__":
    portfolio_root = "C:/projects/skills"
    synced, skipped, errors = sync_portfolio(portfolio_root)
    
    print("\n" + "="*40)
    print("Portfolio Sync Summary")
    print(f"  Successfully Synced: {len(synced)}")
    print(f"  Skipped:             {len(skipped)}")
    print(f"  Errors:              {len(errors)}")
    print("="*40)
    
    if synced:
        print("\n[+] Synced Repos:")
        for s in synced: print(f"  - {s}")

    if errors:
        print("\n[!] Error Repos:")
        for e in errors: print(f"  - {e}")
