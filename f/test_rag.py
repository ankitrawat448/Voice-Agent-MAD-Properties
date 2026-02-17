"""
Test suite for MAD Apartments RAG Knowledge Base
Run: python test_rag.py

Tests the search_knowledge_base function with realistic tenant questions.
Does NOT require Twilio, Deepgram, or any API keys.
Requires: pip install chromadb sentence-transformers
"""
import asyncio
import sys

RESET  = "\033[0m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


# ─────────────────────────────────────────────
# Test queries grouped by document
# ─────────────────────────────────────────────

TEST_QUERIES = [
    # Emergency procedures
    ("What counts as an emergency?",
     ["Emergency Procedures"]),
    ("My boiler is broken in January — is that an emergency?",
     ["Emergency Procedures", "Maintenance Policy"]),
    ("There's a gas smell in my flat. What should I do?",
     ["Emergency Procedures"]),
    ("How long will it take for someone to arrive for a burst pipe?",
     ["Emergency Procedures"]),
    ("What should I do while waiting for the emergency team after a flood?",
     ["Emergency Procedures"]),

    # Maintenance policy
    ("How long does a routine repair take?",
     ["Maintenance Policy"]),
    ("Who is responsible for fixing my boiler?",
     ["Maintenance Policy", "Tenant Rights And Escalation"]),
    ("Do I have to pay for repairs in my flat?",
     ["Maintenance Policy"]),
    ("The mould in my bedroom is getting worse. What will happen?",
     ["Maintenance Policy", "Tenant Rights And Escalation"]),
    ("My landlord-provided washing machine is broken. Will you fix it?",
     ["Maintenance Policy"]),

    # Tenant rights and escalation
    ("What are my rights as a tenant?",
     ["Tenant Rights And Escalation"]),
    ("How do I escalate my complaint if it isn't resolved?",
     ["Tenant Rights And Escalation"]),
    ("What can I do if repairs are never done?",
     ["Tenant Rights And Escalation"]),
    ("How do I contact the Housing Ombudsman?",
     ["Tenant Rights And Escalation"]),
    ("My neighbour is making noise every night. What happens?",
     ["Tenant Rights And Escalation"]),
    ("Who handles pest control in the building?",
     ["Tenant Rights And Escalation", "Maintenance Policy"]),
]


async def run_tests():
    from rag_engine import build_index, search_knowledge_base

    print(f"\n{BOLD}MAD Apartments — RAG Knowledge Base Tests{RESET}")
    print("=" * 60)
    print(f"{DIM}Building index…{RESET}")

    total_chunks = await build_index()
    print(f"{GREEN}✓ Index ready: {total_chunks} chunks{RESET}\n")

    passed = 0
    failed = 0

    for query, expected_sources in TEST_QUERIES:
        result = await search_knowledge_base(query)

        # Check success
        ok = result.get("success", False)

        # Check that at least one expected source appears in returned sources
        returned  = [s.lower() for s in result.get("sources", [])]
        hit = ok and any(
            any(exp.lower() in r for r in returned)
            for exp in expected_sources
        )

        icon = f"{GREEN}✓{RESET}" if hit else f"{RED}✗{RESET}"
        if hit:
            passed += 1
        else:
            failed += 1

        print(f"{icon} {query}")
        if result.get("sources"):
            print(f"   {DIM}Sources: {result['sources']}{RESET}")

        # Show first 200 chars of answer
        answer = result.get("answer", "")
        if answer:
            snippet = answer[:200].replace("\n", " ")
            print(f"   {CYAN}{snippet}…{RESET}")

        if not hit:
            print(f"   {YELLOW}Expected sources containing: {expected_sources}{RESET}")
            if not ok:
                print(f"   {RED}Error: {result.get('answer')}{RESET}")

        print()

    print("=" * 60)
    total = passed + failed
    colour = GREEN if failed == 0 else YELLOW if failed < 3 else RED
    print(f"{colour}{BOLD}{passed}/{total} tests passed{RESET}")

    if failed > 0:
        print(f"{YELLOW}Note: Some misses are expected if chunk boundaries split relevant content.{RESET}")

    return failed


async def interactive():
    """Type queries and see raw RAG results."""
    from rag_engine import build_index, search_knowledge_base

    print(f"\n{BOLD}Interactive RAG Search{RESET}")
    await build_index()

    while True:
        print(f"\n{CYAN}Enter query (or 'quit'):  {RESET}", end="")
        q = input().strip()
        if q.lower() in ("quit", "exit", "q", ""):
            break

        result = await search_knowledge_base(q)

        if result["success"]:
            print(f"\n{BOLD}Sources:{RESET} {result['sources']}")
            print(f"\n{BOLD}Answer:{RESET}")
            print(result["answer"])
        else:
            print(f"{RED}No result: {result['answer']}{RESET}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode in ("-i", "--interactive"):
        asyncio.run(interactive())
    else:
        failures = asyncio.run(run_tests())
        sys.exit(0 if failures == 0 else 1)
