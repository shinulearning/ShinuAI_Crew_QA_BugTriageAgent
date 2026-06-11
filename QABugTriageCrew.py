"""QA Bug Triage Agents — Each agent is a specialist."""

from crewai import Agent, Task, Crew, Process
from crewai import LLM
from dotenv import load_dotenv
import os
import requests

load_dotenv()


# Workaround: CrewAI 1.14.6 attaches a `cache_breakpoint` field to chat
# messages that Groq's OpenAI-compatible endpoint rejects. Strip it before
# every call.
class GroqLLM(LLM):
    def call(self, messages, *args, **kwargs):
        if isinstance(messages, list):
            cleaned = []
            for m in messages:
                if isinstance(m, dict):
                    m = {k: v for k, v in m.items() if k != "cache_breakpoint"}
                cleaned.append(m)
            messages = cleaned
        return super().call(messages, *args, **kwargs)

# Step 0 - Setup the Brain (GPT-OSS 120B via Groq)
groq_llm = GroqLLM(
    model="openai/openai/gpt-oss-120b",
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_KEY"),
)

# Agent 1: Bug Triage Analyst
# Agent 2: Root Cause Investigator
# Agent 3: Test Recommendation Agent

# Task 1: Classify the bug
# Task 2: Investigate root cause (uses triage output as context)
# Task 3: Recommend tests (uses both previous outputs)


# How to fetch from the JIRA?
# JIRA API

def _extract_atlassian_text(node):
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        return "".join(_extract_atlassian_text(child) for child in node.get("content", []))
    if isinstance(node, list):
        return "".join(_extract_atlassian_text(item) for item in node)
    return ""


def fetch_jira_ticket(bug_id):
    jira_email = os.getenv("JIRA_EMAIL")
    jira_token = os.getenv("JIRA_API_TOKEN")
    jira_base_url = os.getenv("JIRA_BASE_URL", "https://shinulearning1.atlassian.net").rstrip("/")

    if not jira_email or not jira_token:
        print("❌ JIRA_EMAIL or JIRA_API_TOKEN is missing. Using sample bug report instead.")
        return None

    try:
        url = f"{jira_base_url}/rest/api/3/issue/{bug_id}"
        r = requests.get(
            url,
            auth=(jira_email, jira_token),
            headers={"Accept": "application/json"},
            params={"fields": "summary,description,reporter"},
            timeout=10,
        )
        if r.status_code == 404:
            print(f"❌ JIRA issue {bug_id} not found at {jira_base_url}. Using sample bug report instead.")
            return None
        if r.status_code in (401, 403):
            print(f"❌ JIRA authentication failed (status {r.status_code}). Check JIRA_EMAIL/JIRA_API_TOKEN. Using sample bug report instead.")
            print("Response:", r.text)
            return None

        r.raise_for_status()
        data = r.json()
        f = data.get("fields", {})

        desc = _extract_atlassian_text(f.get("description", {})).strip() or "No description provided"
        reporter = f.get("reporter", {}).get("displayName", "Unknown")
        summary = f.get("summary", "No title provided")

        return f"""Bug Title: {summary}
Bug ID: {data.get('key', bug_id)}
Reporter: {reporter}

{desc}"""
    except requests.exceptions.Timeout:
        print("❌ JIRA API request timed out. Using sample bug report instead.")
        return None
    except ValueError as ve:
        print(f"❌ Failed to decode JIRA response: {ve}. Using sample bug report instead.")
        print("Response body:", getattr(r, 'text', 'n/a'))
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ JIRA request failed: {e}. Using sample bug report instead.")
        return None
    except Exception as e:
        print(f"❌ Unexpected error fetching JIRA ticket: {e}. Using sample bug report instead.")
        return None

# Try to fetch from JIRA, fallback to sample if it fails
bug_report = fetch_jira_ticket("SCRUM-5")

# Sample bug report fallback
if bug_report is None:
    bug_report = """
Bug Title: BUG-001: User Authority Verification Failure
Bug ID: SCRUM-5
Reporter: shinu n
Environment: Production
Severity (Reporter): Critical

Steps to Reproduce:
- Login as Viewer role user.
- Navigate to Administration → User Management.
- Edit an existing user profile.
- Save changes.

Actual Result: System allows user modifications without validating authority.
Expected Result: Viewer users should have read-only access and should not be able to modify user information.

Additional Info:
- During validation of role-based access control, users assigned with "Viewer" role were able to access the User Management page and perform edit operations.
- Environment : QA Environment, Build 5.2.1
"""

print("📌 Bug Report:")
print(bug_report)


# Agent 1: Bug Triage Analyst
bug_analyst = Agent(
    role="Senior Bug Triage Analyst",
    goal="Accurately classify incoming bugs by severity, category, and priority",
    backstory="""You are a Senior QA engineer with 15 years of experience.
    You follow strict severity classification:
    - P0 (Blocker): System down, data loss, security breach
    - P1 (Critical): Major feature broken, no workaround
    - P2 (Major): Feature impaired, workaround exists
    - P3 (Minor): Cosmetic issue, minor inconvenience
    - P4 (Trivial): Enhancement request, typo
    You never inflate severity. You always justify your classification.""",
    llm=groq_llm,
    verbose=True,
    allow_delegation=False # This agent handles its own work
)
# Agent 2: Root Cause Investigator
root_cause_agent = Agent(
    role="Root Cause Analysis Specialist",
    goal="Identify the likely root cause and affected system components",
    backstory="""You are a debugging expert who thinks in system layers.
    You analyze bugs by tracing through: UI → API → Service → Database → Environment.
    You identify whether the issue is in frontend, backend, 
    infrastructure, or third-party integration. You suggest which 
    log files or monitoring dashboards to check first.""",
    llm=groq_llm,
    verbose=True,
    allow_delegation=False
)
# Agent 3: Test Recommendation Agent
test_recommender = Agent(
    role="Test Strategy Advisor",
    goal="Recommend specific tests to validate the fix and prevent regression",
    backstory="""You are an expert SDET who designs test strategies.
    For every bug, you recommend:
    1. Immediate smoke tests to verify the fix
    2. Regression test cases to prevent recurrence
    3. Edge cases that should be added to the test suite
    You Identify and provide details of Test cases in JIRA Zephyr format to enter to JIRA when applicable.""",
    llm=groq_llm,
    verbose=True,
    allow_delegation=False
)


triage_task = Task(
    description=f"""Analyze and classify this bug report:
        
        {bug_report}
        
        Provide:
        1. Severity (P0-P4) with justification
        2. Category (UI, Functional, Performance, Security, Data)
        3. Affected component/module
        4. Business impact assessment
        5. Recommended priority for sprint planning""",
        
    expected_output="""A structured triage report with severity, 
        category, component, business impact, and sprint priority.""",
    agent=bug_analyst
)

# Task 2: Investigate root cause (uses triage output as context)
root_cause_task = Task(
    description=f"""Based on the triage analysis, investigate the 
    likely root cause of this bug:
    
    {bug_report}
        
        Provide:
        1. Most likely root cause
        2. System layer affected (UI/API/Service/DB/Infra)
        3. Related components that might be impacted
        4. Suggested investigation steps
        5. Which logs/dashboards to check first""",
        
    expected_output="""A root cause analysis report with the probable 
    cause, affected layer, related components, and investigation steps.""",
    agent=root_cause_agent,
    context=[triage_task]  # Receives output from triage
)

test_task = Task(
    description=f"""Based on the triage and root cause analysis, 
    recommend test cases for this bug:
    
    {bug_report}
        
        Provide:
        1. Verification test (confirm the fix works)
        2. 1-2 regression test cases
        3. 1-2 Edge cases to add to the test suite
        4. Any 1 load/performance tests if applicable
        You need to create only very Important 2-3 Test cases and which should cover the main scenarios """,
        
    expected_output="""A test recommendation report with verification 
    tests, regression cases, and edge cases.""",
    agent=test_recommender,
    context=[triage_task, root_cause_task]  # Uses both outputs
)

crew = Crew(
    agents=[bug_analyst, root_cause_agent, test_recommender],
    tasks=[triage_task, root_cause_task, test_task],
    process=Process.sequential,
    verbose=True
)

print("🔍 QA Bug Triage Crew — Starting Analysis")
print("=" * 60)

result = crew.kickoff()
print("\n" + "=" * 60)
print("📋 FINAL TRIAGE REPORT")
print("=" * 60)
print(result)