# **RAVen**

<u>R</u>eal-world <u>A</u>utomated <u>V</u>alidation of R<u>e</u>factori<u>n</u>gs

RAVen is an experimental infrastructure for validating real-world refactorings and reproducing the historical Java/Maven environments in which they occurred.

The repository supports an ongoing empirical study on automated refactoring.

## Study Status

This repository supports an ongoing empirical study.

The dataset, candidate set, scripts, experimental configuration, and results may change while the study is in progress.

A stable version of the repository will be archived when the final experimental dataset and results are established.

## Workflow

The current workflow is organized into two main stages:

```text
Candidate transition
        ↓
Candidate validation
        ↓
Valid historical refactoring
        ↓
Historical commit reproduction
        ↓
Codex environment reconstruction
        ↓
Offline Maven validation
        ↓
Reproducible benchmark instance
```

Candidate validation determines whether a transition represents a valid smell-removal refactoring.

Historical commit reproduction is performed separately and determines whether the commit containing the smell can be successfully built and tested in a reconstructed environment.

## Requirements

RAVen requires:

- Python 3;
- Git;
- Codex CLI;
- DesigniteJava;
- RefactoringMiner;
- local Java and Maven toolchains prepared by RAVen.

The Codex CLI must be installed, configured, and authenticated before running the reproduction pipeline.

## Prepare Environment

The project uses local Java and Maven installations stored under:

```text
benchmark/toolchains/
```

To download the required toolchains, run:

```bash
./prepare_toolchains.sh
```

The script prepares the following toolchains:

### Java

- Temurin 8
- Temurin 11
- Temurin 17
- Temurin 21
- Temurin 23

### Maven

- 3.2.5
- 3.8.3
- 3.8.4
- 3.8.8
- 3.9.6

Downloaded toolchains are not versioned in Git.

## Candidate Validation

Historical smell-removal candidates are validated before build reproduction.

### Input

The validation pipeline receives candidate transitions containing information such as:

- repository;
- smell;
- target entity;
- commit containing the smell (`C`);
- subsequent commit where the smell appears to have been removed (`C'`).

The currently considered smells are:

- Insufficient Modularization (IM);
- Hub-like Modularization (HM);
- God Component (GC);
- Unstable Dependency (UD).

### Validation Criteria

A candidate is retained only when all of the following conditions hold:

1. `C'` is a direct child of `C`;
2. the target entity still exists in `C'`;
3. DesigniteJava detects the smell in `C`;
4. DesigniteJava does not detect the smell in `C'`;
5. RefactoringMiner identifies at least one refactoring involving the target entity in the transition.

Build reproducibility is evaluated separately after candidate validation.

### Validate One Candidate

A single candidate can be validated with:

```bash
python validate_pair.py \
  --repo <repository-url> \
  --c <commit-with-smell> \
  --cprime <commit-without-smell> \
  --smell <IM|HM|GC|UD> \
  --fqn <target-entity>
```

### Validate a Candidate Dataset

Candidate datasets can be validated with:

```bash
python validate_candidates.py
```

Validation artifacts are stored under:

```text
candidate_validation/
```

This directory may contain:

```text
candidate_validation/
├── designite/       cached DesigniteJava results
├── refactorings/    RefactoringMiner results
├── pairs/           pair-level validation artifacts
└── results.csv      consolidated validation results
```

## Historical Commit Reproduction

After candidate validation, RAVen attempts to reproduce the environment of the historical commit containing the smell.

To reproduce a single commit:

```bash
python repro.py \
  --repo https://github.com/example/project.git \
  --commit <commit-sha>
```

RAVen attempts to reconstruct the build environment without modifying tracked project files.

The historical commit is treated as the artifact to reproduce. The objective is to reconstruct a compatible environment, not to repair the project.

## Codex

RAVen uses the Codex CLI to investigate and reconstruct build environments for historical commits.

Codex receives the target repository and commit together with reproduction instructions defined by RAVen.

During environment reconstruction, Codex may inspect:

- source files;
- `pom.xml` files;
- Maven configuration;
- Maven wrapper files;
- CI configuration;
- repository history;
- Java and Maven requirements;
- dependency metadata;
- previous project versions;
- historical dependency sources.

Codex may adjust the external reproduction environment, including Java and Maven versions, Maven settings, profiles, properties, toolchains, environment variables, and isolated dependency repositories.

Codex must not modify tracked project source files, tests, POM files, wrapper files, or CI files merely to make the historical build pass.

The environment produced by Codex is subsequently validated by RAVen outside the Codex execution.

## Reproduction Output

Each reproduction environment is stored under:

```text
benchmark/repositories/<repository>/commits/<commit>/
```

A generated environment may contain:

```text
m2/               isolated Maven repository
dependency-src/   reconstructed dependency sources, when required
logs/             reproduction-specific logs
AGENTS.md          instructions provided to Codex
manifest.txt       reproduction status and metadata
reproduce.sh       executable reproduction script
settings.xml       Maven settings, when required
```

The repository checkout itself is stored separately under:

```text
benchmark/repositories/<repository>/repository/
```

## Reproduction Validation

A reproduction is considered successful only when the generated environment can execute the historical commit tests successfully in offline mode.

The final validation is equivalent to:

```bash
mvn -o clean test
```

using the Java, Maven, Maven repository, settings, profiles, properties, and environment reconstructed for the historical commit.

The final validation is executed outside the Codex session.

An online execution of the same reconstructed environment can also be performed by removing Maven's offline option while preserving the remaining environment configuration.

Offline execution is used as the reproducibility criterion.

## Batch Execution

Multiple historical commits can be processed using:

```bash
./run_batch.sh
```

The batch runner reads the configured commit dataset and invokes the reproduction pipeline for each target commit.

Previously completed successful reproductions can be reused instead of being reconstructed again.

## Tools

External analysis tools used by the study are stored or expected under:

```text
tools/
```

The current pipeline uses:

- **DesigniteJava** for design and architecture smell detection;
- **RefactoringMiner** for detecting refactorings between commits.

For example:

```text
tools/
├── DesigniteJava.jar
└── RefactoringMiner-*/
```

Large third-party binaries may not be versioned in Git.

The versions used in the final study should be preserved in the corresponding experimental release.

## Logs

Execution logs are stored under:

```text
log/
```

This directory contains logs generated during batch processing and historical environment reproduction.

Repository-specific and batch-level logs can be used to inspect failures and execution progress.

Logs are execution artifacts and are not required to execute RAVen.

## Repository Structure

A simplified view of the repository is:

```text
RAVen/
├── candidate_validation/
│   ├── designite/
│   ├── refactorings/
│   ├── pairs/
│   └── results.csv
│
├── benchmark/
│   ├── repositories/
│   │   └── <repository>/
│   │       ├── repository/
│   │       └── commits/
│   ├── results/
│   └── toolchains/
│       ├── java/
│       └── maven/
│
├── log/
├── tools/
│
├── AGENTS.md
├── CODEX_PROMPT.md
├── prepare_toolchains.sh
├── repro.py
├── run_batch.sh
├── collect_results.py
├── validate_pair.py
└── validate_candidates.py
```

## Scope

RAVen currently targets historical Java projects built with Maven.

The reproduction pipeline focuses on reconstructing the environment required by a historical commit.

RAVen does not modify tracked project artifacts merely to obtain a successful build.

Target projects using unsupported build systems are outside the current reproduction scope.

## Reproducibility Principle

The generated `reproduce.sh` acts as an executable description of the reconstructed historical environment.

A successful reproduction should remain executable using:

- the selected local Java toolchain;
- the selected local Maven version;
- the isolated Maven repository;
- any required Maven settings;
- any required profiles and properties;
- any required environment variables;

without requiring changes to the tracked contents of the historical commit.