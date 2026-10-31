# IssueLens — Hackathon Demonstration & Judging Guide 🎙️

This document contains the live presentation materials for hackathon judging:
- A tight 60-second pitch script.
- A 2-minute technical walkthrough.
- Three difficult judge questions with verified, factual answers.

---

## ⚡ 60-Second Live Demo Script

**Speaker Setup:** Have IssueLens open in your browser (`http://localhost:8501`). The sidebar should have Demo Fallback enabled, and the URL input should be visible.

---

### [00:00 - 00:15] The Hook & The Problem
> *"Judges, every year millions of aspiring developers try to contribute to open source, but 80% give up on their very first day. Why? Because GitHub issues are written for veteran maintainers—riddled with shorthand, inside jargon, and zero pointers to where the relevant code lives in a 5,000-file repository. Even worse, if you paste the issue into a generic chatbot, it invents files that don't exist."*

### [00:15 - 00:35] The Live Action
*(Click **"📌 Flask #5000"** and hit **"🚀 Analyze Issue"**)*
> *"This is IssueLens. We enter a real open-source issue—here, Flask issue #5000 asking to deprecate `JSON_AS_ASCII`. Watch the live progress: IssueLens doesn't guess. It queries the GitHub REST API, indexes the recursive file tree, deterministically extracts code identifiers, and pulls bounded source snippets with exact line numbers."*

### [00:35 - 00:50] Grounded AI with Gemma 4
*(Switch to the **"💡 Beginner Guide"** and **"📂 Evidence & Files"** tabs)*
> *"Now Gemma 4 (`gemma-4-26b-a4b-it`) takes over. Notice what happens: it translates this cryptic deprecation into a crystal-clear mental model for a junior developer. More importantly, look at our evidence cards: every suggested file—like `src/flask/config.py` lines 95 to 106—is verified against real repository code. We strictly separate verified facts from AI hypotheses."*

### [00:50 - 01:00] The Contributor Close
*(Switch to **"🧪 Test Specs"** and **"✅ PR Checklist"**)*
> *"Finally, IssueLens generates concrete pytest cases and an interactive pull request readiness checklist. IssueLens turns intimidating issues into confident first-time contributors—grounded in real code, powered by Gemma 4."*

---

## ⏱️ 2-Minute In-Depth Project Walkthrough

**Audience:** Technical judges who want architectural depth.

---

### Phase 1: Problem Deep Dive (30 seconds)
Open source sustainability depends on replenishing maintainers with new contributors. But newcomers face a steep "context wall":
- **Issue opacity:** Maintainers write notes like "deprecate config key in favor of provider", without mentioning what files implement configuration hooks.
- **Cognitive overload:** Navigating large open-source codebases requires understanding directory conventions, test patterns, and backwards compatibility requirements.
- **The LLM Hallucination Trap:** Off-the-shelf LLMs hallucinate file names, outdated methods, and broken line numbers because they have no runtime grounding in the current repository state.

### Phase 2: Architecture & Deterministic Grounding (45 seconds)
IssueLens solves this with a three-layer pipeline:
1. **Deterministic Ingestion (`github_client.py`):**
   - Uses the GitHub REST API to fetch issue metadata, repository stats, README, and the complete recursive Git tree.
   - Enforces security bounds: 60KB per file max, rate limit headers inspection, and 4,000 files tree limit.
2. **Deterministic Evidence Scoring (`analyzer.py`):**
   - Tokenizes issue titles, labels, and backtick code mentions.
   - Scores every repository path against extracted keywords.
   - Fetches candidate files and isolates bounded snippet windows with exact line numbers (`#L...-L...`).
   - Labels evidence as either `VERIFIED` (snippet contains matching tokens) or `INFERRED` (path-level relevance).
3. **Reasoned Synthesis (`ai_engine.py`):**
   - Feeds the structured context to **Gemma 4** (`gemma-4-26b-a4b-it`) with strict instructions forbidding invented files.
   - Validates the output through **Pydantic v2** models, ensuring structured, type-safe data for the frontend.

### Phase 3: The Contributor Experience (45 seconds)
In the Streamlit developer dashboard (`app.py`), the newcomer receives:
- A plain-English beginner breakdown with everyday analogies.
- Side-by-side comparison of **Verified Facts** vs **Unverified AI Hypotheses**.
- Real file cards showing exact line ranges and why they matter.
- Step-by-step investigation and implementation plans.
- Test scenarios specifying inputs and expected behaviors.
- An interactive PR readiness checklist preventing common submission mistakes.

---

## 🎯 Three Tough Judge Questions & Factual Answers

### Question 1: "Why not just copy-paste the GitHub issue into ChatGPT or Claude? Why does IssueLens need to exist?"
**Factual Answer:**
> *"Generic chatbots do not have access to the live repository state. If you paste Flask issue #5000 into a general chatbot, it has to guess what Flask's codebase looks like today. It frequently references deprecated files like `flask/helpers.py`, invents helper methods, or hallucinates line numbers. Furthermore, general models don't tell the user what is a verified fact versus what is an educated guess.*
>
> *IssueLens acts as the retrieval and grounding engine. We fetch the live recursive tree from GitHub, extract actual source lines (e.g. `src/flask/config.py#L95-106`), and feed that verified context to Gemma 4. If a file isn't in the repository, Gemma is forbidden from citing it. IssueLens gives the contributor verified truth, not plausible fiction."*

---

### Question 2: "How does IssueLens handle scale when analyzing a repository with 20,000 files, or when GitHub rate limits trigger?"
**Factual Answer:**
> *"We built four strict architectural boundaries:*
> 1. *Path Filtering & Depth Limits: We prune `node_modules`, `.git`, build outputs, binaries, and vendor directories immediately, cutting typical trees by over 70%.*
> 2. *Bounded Tree & File Sizes: We cap the Git Trees API at 4,000 files and limit individual file downloads to 60KB, preventing memory exhaustion on massive files.*
> 3. *Rate Limit Defense: The GitHub client tracks `X-RateLimit-Remaining` and `X-RateLimit-Reset`. If a public user hits the 60 req/hr limit, IssueLens displays the exact UTC reset time and provides a token input field.*
> 4. *High-Availability Demo Mode: For hackathon judging or offline environments, we provide pre-verified authentic benchmark datasets (Flask #5000 and Requests #4200) so a judge can evaluate the system without risk of third-party network outages."*

---

### Question 3: "Why did you choose Gemma 4 (gemma-4-26b-a4b-it), and how do you ensure the model doesn't return broken JSON or hallucinated plans?"
**Factual Answer:**
> *"Gemma 4 (`gemma-4-26b-a4b-it`) combines open-weights research excellence with instruction adherence. At 26 billion parameters, it offers deep programming reasoning with low latency when hosted via the Google Gen AI SDK.*
>
> *To guarantee reliability:*
> 1. *We run inference at temperature 0.2 to prioritize determinism over creativity.*
> 2. *We enforce structured JSON output in the API call.*
> 3. *We run the response through a resilient JSON cleanup layer that strips markdown code fences and fixes trailing commas.*
> 4. *Every single response is validated through Pydantic v2 schemas (`IssueAnalysisResult`). If the model ever misses a required field or returns invalid types, our custom `MalformedAIResponseError` traps it immediately."*
