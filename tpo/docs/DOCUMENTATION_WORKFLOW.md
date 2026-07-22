# Documentation Workflow

## Purpose

This document defines the standard lifecycle for all major TPO documentation.

The goal is to ensure that architectural decisions are made once, reviewed consistently, and frozen before implementation continues.

---

# Document Lifecycle

Every major document follows the same lifecycle.

```text
Draft
↓
Architecture Review
↓
Editing
↓
Freeze Review
↓
Frozen
```

---

# 1. Architecture Review

## Purpose

Define the content of the document.

Allowed:

- Architecture
- Responsibilities
- Boundaries
- Concepts
- Structure

Everything may be questioned.

---

# 2. Editing

## Purpose

Apply the approved decisions.

Allowed:

- Rewrite
- Improve clarity
- Improve structure
- Improve consistency

Not allowed:

- New architectural ideas
- New concepts
- New responsibilities

---

# 3. Freeze Review

## Purpose

Verify that the document is ready to become official.

Review only:

- Clarity
- Terminology
- Consistency
- Redundancy
- Onboarding
- Document responsibility

Architectural redesign is not allowed.

---

# 4. Freeze

## Purpose

Make the document official.

Requirements:

- Dedicated freeze commit
- Clean working tree
- Document considered stable

---

# Frozen Documents

Frozen documents are not modified for stylistic improvements.

They are reopened only when a new architectural decision requires it.

---

# Review Rule

Each review must have one objective only.

Do not mix:

- Architecture
- Implementation
- Editorial improvements

Each review should answer one question only.

---

# Guiding Principle

Simple documentation.

Clear responsibilities.

Stable architecture.
