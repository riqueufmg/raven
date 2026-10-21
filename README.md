# **RAVen**

<u>R</u>eal-world <u>A</u>utomated <u>V</u>alidation of R<u>e</u>factori<u>n</u>gs

RAVen is an experimental infrastructure for mining and validating real-world refactorings and reproducing the historical Java/Maven environments in which they occurred.

The repository supports an ongoing empirical study on automated refactoring.

## Study Status

This repository supports an ongoing empirical study.

The dataset, candidate set, scripts, experimental configuration, and results may change while the study is in progress.

A stable version of the repository will be archived when the final experimental dataset and results are established.

## Workflow

The current workflow is organized into three main stages:

```text
Repository history
        ↓
Smell-removal mining
        ↓
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

Mining identifies transitions in which a design or architecture smell disappears between analyzed commits.

Candidate validation determines whether a transition represents a valid smell-removal refactoring.

Historical commit reproduction is performed separately and determines whether the commit containing the smell can be successfully built and tested in a reconstructed environment.

## Requirements

The complete RAVen pipeline may require:

- Python 3;
- Git;
- DesigniteJava;
- RefactoringMiner;
- Codex CLI;
- local Java and Maven toolchains prepared by RAVen.

Not every stage requires every dependency. Smell mining uses Git, Python, and DesigniteJava. Candidate validation additionally uses RefactoringMiner. Historical commit reproduction uses Codex CLI and the local Java/Maven toolchains.

The Codex CLI must be installed, configured, and authenticated before running the reproduction pipeline.

## Prepare Environment

The reproduction stage uses local Java and Maven installations stored under:

```text
benchmark/toolchains/
```

To download the required toolchains, run:

```bash
./prepare_toolchains.sh
```

The script prepares the following toolchains.

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

# Build/Extend the Benchmark

RAVen provides the scripts used to construct and extend the benchmark from repository histories.

The process starts by mining candidate smell-removal transitions, validates the resulting commit pairs, and finally reconstructs the historical build environment of selected commits.

## 1. Mine Candidate Transitions

The mining pipeline is located under:

```text
mining/
```

It analyzes Java repositories with DesigniteJava and identifies transitions in which one of the considered smells disappears.

The currently considered smells are:

- Insufficient Modularization (IM);
- Hub-like Modularization (HM);
- God Component (GC);
- Unstable Dependency (UD).

### Mining Input

The repository list is stored in:

```text
mining/repositories.csv
```

The current list contains repository metadata used by the batch runner, including repository name, default branch, commit count, and language metrics.

The batch runner orders pending repositories using the heuristic:

```text
commit count × Java LOC
```

Repositories with existing result directories are skipped.

### Mining Layout

Mining artifacts are kept separate from benchmark reproduction artifacts:

```text
mining/
├── repositories.csv
├── search_candidates.py
├── analyze_results.py
├── collect_smell_candidates.py
├── run_search_batch.sh
├── repositories/          local repository clones
├── results/               DesigniteJava and candidate outputs
└── log/                   mining logs
```

The local clone, result, and log directories are execution artifacts and are not versioned.

DesigniteJava is shared with the rest of RAVen through:

```text
tools/DesigniteJava.jar
```

### Preview a Mining Batch

Before starting a batch, the selected repositories can be inspected without cloning or analyzing anything:

```bash
./mining/run_search_batch.sh 20 3 --dry-run
```

The first argument is the maximum number of repositories selected for the batch and the second is the number of parallel workers.

The dry run prints the execution queue and writes:

```text
mining/repos_to_run_sorted.tsv
```

without cloning repositories or invoking DesigniteJava.

### Run a Mining Batch

To run the selected repositories:

```bash
./mining/run_search_batch.sh 20 3
```

Each repository is cloned under:

```text
mining/repositories/<repository>/
```

DesigniteJava results are written under:

```text
mining/results/<repository>/
```

and the corresponding execution log is written under:

```text
mining/log/<repository>.log
```

The batch uses regular DesigniteJava commit analysis (`-ac`).

### Analyze One Repository

After DesigniteJava finishes processing a repository, candidate transitions for all four smells can be extracted with:

```bash
python -m mining.analyze_results \
  --repo mining/repositories/<repository> \
  --results-root mining/results \
  --branch refs/heads/<branch>
```

The generated files are stored under:

```text
mining/results/<repository>/candidates/
├── IM_candidates.csv
├── HM_candidates.csv
├── GC_candidates.csv
└── UD_candidates.csv
```

A `smell_removed_candidate` represents a direct parent-child transition in which the target entity still exists after the transition and the smell is no longer reported in the subsequent analyzed commit.

These mining results are candidate transitions only. They do not by themselves establish that a refactoring removed the smell.

### Consolidate Candidates

Candidate files produced for individual repositories can be consolidated with:

```bash
python -m mining.collect_smell_candidates \
  --results-root mining/results
```

The consolidated candidate set is used as input to the validation stage.

## 2. Validate Candidate Transitions

Historical smell-removal candidates are validated before build reproduction.

### Input

The validation pipeline receives candidate transitions containing information such as:

- repository;
- smell;
- target entity;
- commit containing the smell (`C`);
- subsequent commit where the smell appears to have been removed (`C'`).

### Validation Criteria

A candidate is retained only when all of the following conditions hold:

1. `C'` is a direct child of `C`;
2. the target entity still exists in `C'`;
3. DesigniteJava detects the smell in `C`;
4. DesigniteJava does not detect the smell in `C'`;
5. RefactoringMiner identifies at least one refactoring involving the target entity in the transition.

Build reproducibility is evaluated separately after candidate validation.

### Validate One Candidate

```bash
python validate_pair.py \
  --repo <repository-url> \
  --c <commit-with-smell> \
  --cprime <commit-without-smell> \
  --smell <IM|HM|GC|UD> \
  --fqn <target-entity>
```

### Validate a Candidate Dataset

```bash
python validate_candidates.py
```

Validation artifacts are stored under:

```text
candidate_validation/
├── designite/       cached DesigniteJava results
├── refactorings/    RefactoringMiner results
├── pairs/           pair-level validation artifacts
└── results.csv      consolidated validation results
```

## 3. Reproduce Historical Commits

After candidate validation, RAVen attempts to reproduce the environment of the historical commit containing the smell.

To reproduce a single commit:

```bash
python repro.py \
  --repo https://github.com/example/project.git \
  --commit <commit-sha>
```

RAVen attempts to reconstruct the build environment without modifying tracked project files.

The historical commit is treated as the artifact to reproduce. The objective is to reconstruct a compatible environment, not to repair the project.

### Codex Environment Reconstruction

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

### Reproduction Output

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

### Reproduction Validation

A reproduction is considered successful only when the generated environment can execute the historical commit tests successfully in offline mode.

The final validation is equivalent to:

```bash
mvn -o clean test
```

using the Java, Maven, Maven repository, settings, profiles, properties, and environment reconstructed for the historical commit.

The final validation is executed outside the Codex session.

An online execution of the same reconstructed environment can also be performed by removing Maven's offline option while preserving the remaining environment configuration.

Offline execution is used as the reproducibility criterion.

### Batch Reproduction

Multiple historical commits can be processed using:

```bash
./run_batch.sh
```

The batch runner reads its input from:

```text
commits.csv
```

The expected columns are:

```text
repository,url,commit
```

For example:

```csv
repository,url,commit
byte-buddy,https://github.com/raphw/byte-buddy.git,ae380bb57643eae40a2ffa7553e6093e256050a7
dropwizard,https://github.com/dropwizard/dropwizard.git,9e256a...
spring-batch,https://github.com/spring-projects/spring-batch.git,667a92...
```

The input file contains the historical commits selected for environment reproduction. For each row, `run_batch.sh` invokes the reproduction pipeline for commit `C`.

The files involved in this stage follow this workflow:

```text
mining candidate transitions
        ↓
validate_candidates.py
        ↓
candidate_validation/results.csv
        ↓
candidate selection
        ↓
commits.csv
        ↓
run_batch.sh
        ↓
historical commit reproduction
```

`candidate_validation/results.csv` contains the result of applying the candidate-validation filters.

`commits.csv` contains the historical commits selected for build reproduction after candidate validation.

Previously completed environments are reused when possible. Commits with an existing successful reproduction are skipped instead of being reconstructed again.

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

Historical reproduction logs are stored under:

```text
log/
```

Mining logs are stored separately under:

```text
mining/log/
```

These directories contain execution artifacts generated during batch processing, candidate mining, and historical environment reproduction.

Repository-specific and batch-level logs can be used to inspect failures and execution progress.

Logs are execution artifacts and are not required to execute RAVen.

## Repository Structure

A simplified view of the repository is:

```text
RAVen/
├── mining/
│   ├── repositories.csv
│   ├── search_candidates.py
│   ├── analyze_results.py
│   ├── collect_smell_candidates.py
│   ├── run_search_batch.sh
│   ├── repositories/
│   ├── results/
│   └── log/
│
├── candidate_validation/
│   ├── designite/
│   ├── refactorings/
│   ├── pairs/
│   └── results.csv
│
├── benchmark/
│   ├── repositories/
│   ├── results/
│   └── toolchains/
│
├── log/
├── tools/
│
├── commits.csv             commits selected for reproduction
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

The mining and validation pipeline targets design and architecture smell-removal transitions in Java repository histories.

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
