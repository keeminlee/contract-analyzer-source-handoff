# Contract Analyst Agent – Demo Narrative

## Title

**Contract Analyst Agent:  
From Chatbot Over Contracts → Deterministic Contract Intelligence**

Department Demo  
<Your Name>  
MUFG

---

# Part 1 — The Naive Version (Copilot Studio)

### What I'm Showing First

A **baseline Copilot Studio implementation**:

- Contract documents linked to a Knowledge Base
- A strong system prompt
- Structured answer formatting

This is exactly how most enterprise copilots begin.

---

### Demo Question

Example:

> "How does this NDA differ from the standard precedent?"

The system produces a reasonable response.

It might highlight:

- confidentiality scope
- term length
- potential indemnity differences

At first glance this looks impressive.

But under the hood we have three major problems.

---

### Problem 1 — Weak Lineage

The answer is generated from:

- semantic retrieval
- arbitrary chunking
- probabilistic reasoning

We cannot deterministically answer:

- Which clause was used
- Why that clause was selected
- Whether the model skipped something important

---

### Problem 2 — Structural Blindness

Contracts are not text blobs.

They have structure:

- sections
- clauses
- subclauses
- definitions
- tables

Generic RAG ignores this structure.

It retrieves **chunks**, not **clauses**.

---

### Problem 3 — Governance Risk

Enterprise systems require:

- reproducibility
- traceability
- explainability

Generic RAG systems struggle with all three.

---

# Transition

So the question becomes:

**What would a contract-native reasoning system look like?**

That’s the prototype I built.

---

# Part 2 — Contract Analyst Agent Prototype

Instead of:

> Document → Chunk → Retrieval → Answer

we built:

**Document → Spine → Dynamic Retrieval → Evidence → Answer**

This changes everything.

---

# The Core Idea

The system mirrors how contracts are structured.

We build a **document spine**.

The spine represents the contract as structured nodes.

Example node:

- Section
- Clause
- Definition
- Table

Each node has:

- stable span positions
- metadata
- classification

This allows deterministic navigation of the contract.

---

# Architecture Overview

Pipeline:

Bronze → Spine → Retrieval → Router → DAG Tools → Evidence → Answer

Bronze:

- raw document
- extracted text

Spine (Silver):

- structural map of clauses

Dynamic Retrieval:

- query-aware chunking over the spine

Router:

- overview vs precision

DAG Tools:

- clause classifier
- obligation extractor
- playbook comparison

Evidence Packet:

- structured proof for the answer

Answer:

- generated only from evidence

---

# What Makes This Powerful

Three key innovations.

---

## 1 — Canonical Contract Spine

Instead of chunking arbitrarily, we build a structural map.

Each node contains:

- node_id
- type
- span_start
- span_end
- text

This allows precise citations.

Example:

> Clause 4.2 – Confidentiality

We know exactly where it lives.

---

## 2 — Dynamic Retrieval Instead of Static Chunking

Traditional RAG:

- pre-splits documents
- stores static embeddings

Our system:

- builds retrieval chunks dynamically
- based on the spine

Chunks are assembled from neighboring structural nodes.

This preserves semantic structure.

---

## 3 — Evidence Packets

The system produces an **evidence packet** before answering.

It contains:

- retrieved chunks
- span locations
- source nodes

The answer can only use these sources.

This creates **deterministic traceability**.

---

# Demo: Precision Mode

Now let’s ask something specific:

> "Quote the termination clause."

The system:

1. Retrieves relevant spine nodes
2. Builds dynamic chunks
3. Routes to the precision agent
4. Produces an evidence packet
5. Generates an answer citing the clause

Example output:

Termination Clause  
Node: clause_8_1  
Span: 10432–10876

Exact language quoted.

---

# Why This Matters for Enterprise

This architecture enables things generic copilots cannot do reliably.

---

### Deterministic Citations

Every answer traces to:

- node id
- span range
- source chunk

---

### Reproducible Analysis

Same query → same pipeline → same evidence.

---

### Governance & Auditability

Execution traces show:

- retrieval method
- routing decision
- evidence used

---

# Why This Is Pivotal

This project is not just a better chatbot.

It establishes a **domain-native reasoning substrate**.

Once we can reason over contracts deterministically, we can build:

- compliance agents
- playbook enforcement
- obligation extraction
- contract risk scoring
- automated negotiation guidance

---

# Long-Term Vision

This prototype becomes the upstream engine for a future:

**AiDa Marketplace Contract Analyst Agent**

Where:

AiDa handles:

- orchestration
- prompt execution
- enterprise integration

And this system provides:

- deterministic document intelligence

---

# The Key Takeaway

The difference is simple but profound.

Generic systems:

> "Find some text and guess."

Contract Analyst Agent:

> "Navigate the contract, gather evidence, then answer."

---

# Closing

This prototype demonstrates that contract analysis can move from:

**probabilistic chat**

to

**deterministic reasoning over documents.**

And that shift is critical for enterprise-grade AI systems.