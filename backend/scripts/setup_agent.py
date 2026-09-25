"""Create or update Pepper's Anthropic resources: environment, vault, agent, schedules.

This is the control plane. Run it once, and again whenever the agent's
instructions, tools or schedules change. It is safe to re-run: existing
resources are updated in place (a new agent version each time), never
duplicated. The server only reads the IDs it writes to agent_ids.json.

    ANTHROPIC_API_KEY=... python scripts/setup_agent.py [--ids agent_ids.json] [--no-schedules]
"""

import argparse
import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pepper.agent.tools import CUSTOM_TOOLS  # noqa: E402

MODEL = "claude-opus-5"
TIMEZONE = "Asia/Kolkata"

SYSTEM = """You are Pepper, the personal chief of staff to Dev: a consultant surgical oncologist (breast, upper GI, colorectal, HPB, gynae-onc, skin & surface, selected sarcomas; also general surgery, minor procedures and endoscopy) who also founded SciScribe Solutions (products: SciScribe, Aakhyan, Scribe EDC, Apollo, Synthesi.se). Dev lives in India (IST).

Your work is split into three lanes: clinical, company and life. Every escalate and notify call names its lane.

How you work
- Do the work; don't describe it. Handle anything reversible yourself and report briefly at the end.
- Ask Dev (the escalate tool) only when a choice is genuinely theirs: irreversible, public, spends money, affects patient care, or you are unsure. Give concrete options and recommend one. Mark it risky when it is irreversible, public or spends money.
- Use notify sparingly, for things Dev should know now but needn't decide.
- Be brief. Dev reads on a phone between cases.

Clinical rules (strict)
- Never write patient names, hospital/UHID/IP numbers, phone numbers or addresses anywhere: not in messages, files, tool inputs or memory. Refer to patients by case id or age/sex/diagnosis.
- You document, organise and remind. You do not make clinical decisions or give treatment advice as if it were yours.
- Standards: AJCC TNM (current edition per site), FIGO for gynaecological cancers, Clavien-Dindo for complications (ISGPS/ISGLS for pancreas/liver), NCCN for surveillance by default with ICMR consensus where available, unless Dev's hospital protocol says otherwise.
- Clinical information never goes into company content, marketing or product work.

Money rules
- You never move money and never ask for banking passwords or OTPs. You may prepare a payment for Dev to approve in their own bank or UPI app.

Secrets
- API keys are available as environment variables whose values are substituted when requests leave the sandbox. Never print them, write them to files or put them in URLs.
"""

SCHEDULES = [
    {
        "name": "Monday planning",
        "cron": "0 9 * * 1",
        "description": "Plan the week: uptime check, pending decisions, week plan, top 3 priorities.",
        "outcome": "Write this week's plan to /mnt/session/outputs/weekly_plan.md",
        "rubric": """- Covers all three lanes (clinical admin, company, life) with no patient identifiers
- Lists every product's uptime status as checked today, with anything down called out first
- Names exactly three priorities for the week, each with a concrete first step
- Lists pending decisions still waiting on Dev
- Fits on one phone screen per lane; no filler""",
    },
    {
        "name": "Wednesday content",
        "cron": "0 9 * * 3",
        "description": "Draft the week's LinkedIn and X posts and ask Dev to approve them.",
        "outcome": "Draft this week's posts in /mnt/session/outputs/content_batch.md, then escalate them to Dev for approval before anything is scheduled",
        "rubric": """- 3 LinkedIn posts and 4 X posts, each with a suggested day and time (IST)
- Mix of thought leadership and product; matches Dev's voice
- No patient information of any kind, and no clinical details from Dev's own practice
- Every factual claim is accurate and checkable
- An escalate call asks Dev to approve, with options to approve all, approve some, or request rewrites""",
    },
    {
        "name": "Friday review",
        "cron": "0 17 * * 5",
        "description": "Weekly review: done, blockers, next week, renewals, backups.",
        "outcome": "Write the weekly review to /mnt/session/outputs/weekly_report.md",
        "rubric": """- Tasks completed this week, blockers, and next week's priorities
- Domain and certificate renewals due in the next 30 days, soonest first
- Backup status per product, stating whether a restore was actually verified
- Progress against the 8-week plan
- No patient identifiers""",
    },
]


def budget(cents: int | None) -> dict | None:
    if not cents:
        return None
    return {"type": "limit", "max_list_cost": {"amount": str(cents), "currency": "USD"}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="agent_ids.json")
    parser.add_argument("--no-schedules", action="store_true")
    parser.add_argument("--run-budget-cents", type=int, default=300, help="Hard cap per scheduled run (USD cents)")
    args = parser.parse_args()

    path = Path(args.ids)
    ids = json.loads(path.read_text()) if path.exists() else {}
    client = anthropic.Anthropic()

    if not ids.get("environment_id"):
        env = client.beta.environments.create(
            name="pepper", config={"type": "cloud", "networking": {"type": "unrestricted"}},
        )
        ids["environment_id"] = env.id
        print("created environment", env.id)

    if not ids.get("vault_id"):
        vault = client.beta.vaults.create(display_name="Pepper")
        ids["vault_id"] = vault.id
        print("created vault", vault.id)

    agent_config = dict(
        name="Pepper",
        model={"id": MODEL, "effort": "high"},
        system=SYSTEM,
        tools=[{"type": "agent_toolset_20260401", "default_config": {"enabled": True}}, *CUSTOM_TOOLS],
    )
    if ids.get("agent_id"):
        agent = client.beta.agents.update(ids["agent_id"], **agent_config)
        print("updated agent", agent.id, "version", agent.version)
    else:
        agent = client.beta.agents.create(**agent_config)
        print("created agent", agent.id)
    ids["agent_id"] = agent.id
    ids.pop("credential_ids", None)  # superseded: credentials now live in the vault

    if not args.no_schedules:
        deployments = ids.setdefault("deployments", {})
        for schedule in SCHEDULES:
            config = dict(
                name=schedule["name"],
                description=schedule["description"],
                agent=agent.id,  # latest version at each run
                environment_id=ids["environment_id"],
                vault_ids=[ids["vault_id"]],
                budget=budget(args.run_budget_cents),
                initial_events=[{
                    "type": "user.define_outcome",
                    "description": schedule["outcome"],
                    "rubric": {"type": "text", "content": schedule["rubric"]},
                    "max_iterations": 3,
                }],
                schedule={"type": "cron", "expression": schedule["cron"], "timezone": TIMEZONE},
                metadata={"lane": "company", "origin": "scheduled"},
            )
            existing = deployments.get(schedule["name"])
            if existing:
                dep = client.beta.deployments.update(existing, **config)
                print("updated schedule", schedule["name"], dep.id)
            else:
                dep = client.beta.deployments.create(**config)
                print("created schedule", schedule["name"], dep.id)
            deployments[schedule["name"]] = dep.id
            print("  next runs:", getattr(dep.schedule, "upcoming_runs_at", None))

    path.write_text(json.dumps(ids, indent=2) + "\n")
    print("wrote", path)


if __name__ == "__main__":
    main()
