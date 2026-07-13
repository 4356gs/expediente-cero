# Product Definition

## Product

Expediente Cero is an AI-assisted intake workspace for accounting and
administrative firms in Galicia.

## Problem

Client information frequently arrives through fragmented emails, messages,
calls, and attachments. Before professional work can begin, staff must:

1. Understand the requested procedure.
2. Extract relevant facts.
3. Identify missing or contradictory information.
4. Request additional documents.
5. Organize everything into a reviewable case file.

This repetitive intake work consumes professional capacity and creates delays,
but still requires human judgment.

## Target user

The initial user is an employee or professional in a small or midsize Galician
gestoría who receives and prepares client requests before tax, employment,
accounting, or administrative work begins.

## Value proposition

Expediente Cero converts an unstructured client request into a structured,
traceable case file that a qualified professional can review.

It reduces intake preparation time without replacing professional judgment.

## Core workflow

1. A staff member enters a client message and optional document metadata.
2. GPT-5.6 produces a structured intake analysis.
3. Deterministic rules validate required fields and identify contradictions.
4. The system applies a configurable checklist for the selected procedure.
5. GPT-5.6 drafts a follow-up message in Spanish or Galician.
6. A professional reviews, edits, approves, or rejects the result.
7. The system records the model output, validations, and human decision.

## Product principles

- Human approval is mandatory.
- Model output is never treated as authoritative.
- Deterministic checks remain separate from generative reasoning.
- Every relevant decision must be traceable.
- Demonstrations use synthetic data only.
- Spanish and Galician are first-class output languages.
- The MVP prepares cases but never submits official filings.

## Initial procedures

The hackathon MVP supports three representative intake types:

1. Self-employed registration.
2. Employee hiring.
3. Grant or subsidy application.

These are intake templates, not legal or administrative advice.

## Success criteria

The MVP succeeds when a reviewer can:

- submit an unstructured synthetic request;
- obtain a typed analysis;
- see missing information and checklist status;
- generate a follow-up draft;
- approve or reject the result;
- inspect the audit trail;
- complete the entire flow in a working interface.
