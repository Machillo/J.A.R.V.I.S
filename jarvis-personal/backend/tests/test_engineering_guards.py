"""Engineering guards for the repository's own rules (CLAUDE.md §4, §7-§9).

1. Owner configuration stays out of shared Users code. The Owner's private
   configuration is read from environment variables. Instead of grepping for
   personal names (brittle, and it would put names in the repo), each variable
   has a small allowlist of Owner-only modules that may read it. Any other
   reader, especially shared Users code, fails. The absence of personal literals
   in the shared parser and ingestion is covered by
   email_monitor/test_parser_identity_isolation.py.
2. Instruction files are loadable and portable: agents and Skills follow the
   documented Claude Code format, agents only reference project Skills, the
   Skills that CLAUDE.md routes to exist (and vice versa), and nothing points to
   a local machine path or embeds commit SHAs.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
CLAUDE_DIR = REPO / ".claude"

# Owner configuration -> the only modules allowed to read it (all behind Owner-only
# boundaries, or the Owner-role resolution itself).
OWNER_CONFIGURATION = {
    "OWNER_EMAIL": {"email_monitor/service.py", "integrations/ibkr_readonly.py"},
    "OWNER_EMAILS": {"auth/owner_role.py", "email_monitor/service.py", "integrations/ibkr_readonly.py",
                     "scripts/workspace_isolation_check.py"},
    "OWNER_DISPLAY_NAME": {"email_monitor/parser_identity.py", "sports/service.py"},
    "JARVIS_OWN_ACCOUNT_IBANS": {"email_monitor/parser_identity.py"},
    "JARVIS_OWN_ACCOUNT_ALIASES": {"email_monitor/parser_identity.py"},
    "JARVIS_OWN_DEBIT_CARD_LAST4": set(),
    "JARVIS_RECEIVABLE_CONTACTS": {"email_monitor/parser_identity.py"},
    "JARVIS_CARD_ALIASES": {"email_monitor/service.py"},
    "BAC_CARD_CUT_DAY": {"email_monitor/service.py"},
    "PERSONAL_ISOLATION_TEST_EMAIL": {"scripts/finva_personal_isolation_check.py"},
}
# Shared code that DINCR Users run: must never read Owner configuration at all.
SHARED_USERS_CODE = ("user_product/", "email_monitor/parser.py", "email_monitor/popular_pdf.py",
                     "email_monitor/normalization.py", "email_monitor/deduplication.py",
                     "email_monitor/gmail_content.py", "email_monitor/payroll_statement.py",
                     "email_monitor/statement_reconciliation.py", "financial_lifecycle/")


def _runtime_modules():
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND).as_posix()
        if "/tests/" in f"/{relative}" or path.name.startswith("test_") or "__pycache__" in relative:
            continue
        yield relative, path.read_text(encoding="utf-8")


def test_owner_configuration_is_read_only_by_its_owner_only_modules():
    readers = {name: set() for name in OWNER_CONFIGURATION}
    for relative, text in _runtime_modules():
        for name in OWNER_CONFIGURATION:
            if re.search(rf"[\"']{name}[\"']", text):
                readers[name].add(relative)
    unexpected = {name: sorted(found - OWNER_CONFIGURATION[name]) for name, found in readers.items() if found - OWNER_CONFIGURATION[name]}
    assert not unexpected, f"Owner configuration read outside Owner-only modules: {unexpected}"


def test_shared_users_code_never_reads_owner_configuration():
    for name, allowed in OWNER_CONFIGURATION.items():
        assert not [path for path in allowed if path.startswith(SHARED_USERS_CODE)], name


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n") or text.startswith("---\r\n"), f"{path}: frontmatter must open on line 1"
    block = text.split("---", 2)[1]
    fields, current = {}, None
    for line in block.splitlines():
        if re.match(r"^[A-Za-z][\w-]*:", line):
            current, _, value = line.partition(":")
            fields[current.strip()] = value.strip()
        elif current and line.strip().startswith("- "):
            fields[current] = (fields[current] + " " + line.strip()[2:]).strip()
    return fields


def _project_skills() -> set[str]:
    return {path.parent.name for path in (CLAUDE_DIR / "skills").glob("*/SKILL.md")}


def test_project_agents_follow_the_documented_subagent_format():
    agents = sorted((CLAUDE_DIR / "agents").glob("*.md"))
    assert agents
    skills = _project_skills()
    names = set()
    for path in agents:
        fields = _frontmatter(path)
        name = fields.get("name", "")
        assert name and ":" not in name and not name.startswith("-"), path
        assert fields.get("description"), path
        assert name not in names, f"duplicate agent name {name}"
        names.add(name)
        for skill in fields.get("skills", "").split():
            assert skill in skills, f"{path.name} references missing or non-project skill '{skill}'"


def test_project_skills_are_complete_and_routed_from_claude_md():
    skills = _project_skills()
    assert {"dincr-core", "dincr-finance", "dincr-data-integrity", "dincr-release-review"} <= skills
    for skill in skills:
        fields = _frontmatter(CLAUDE_DIR / "skills" / skill / "SKILL.md")
        assert fields.get("description"), skill
    claude_md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    routed = set(re.findall(r"`(dincr-[a-z-]+)`", claude_md))
    assert routed == skills, f"CLAUDE.md routes {sorted(routed)} but .claude/skills has {sorted(skills)}"
    for path in (CLAUDE_DIR / "skills").rglob("*.md"):
        for reference in re.findall(r"`(references/[\w.-]+\.md)`", path.read_text(encoding="utf-8")):
            assert (path.parent / reference).exists() or (CLAUDE_DIR / "skills" / "dincr-finance" / reference).exists(), (path, reference)


def test_instruction_files_are_portable_and_hold_no_ephemeral_identifiers():
    files = [REPO / "CLAUDE.md", *CLAUDE_DIR.glob("agents/*.md"), *CLAUDE_DIR.glob("skills/**/*.md")]
    local_path = re.compile(r"[A-Za-z]:\\\\|/Users/|AppData|/home/|local-agent-mode-sessions")
    sha = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not local_path.search(text), f"{path}: machine-specific path"
        assert "anthropic-skills:" not in text, f"{path}: use the project Skills in .claude/skills"
        assert not sha.search(text), f"{path}: commit SHA in a permanent instruction"
