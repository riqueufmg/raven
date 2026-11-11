# RAVen

**Real-world Automated Validation of Refactorings**

RAVen is a web-based tool for creating benchmarks of design and architecture smell removals in Java projects. It analyzes historical Git commits, identifies and validates candidate smell removals, and reconstructs the build environment of commits containing smells.

RAVen currently supports four smells:

- **IM:** Insufficient Modularization (class)
- **HM:** Hub-like Modularization (class)
- **GC:** God Component (package)
- **UD:** Unstable Dependency (package)

The **RAVen-bench** dataset is distributed separately from this tool.

## Requirements

- Python 3 and Git
- [DesigniteJava](https://www.designite-tools.com/designitejava/) (with a valid license)
- [RefactoringMiner](https://github.com/tsantalis/RefactoringMiner)
- [Codex CLI](https://github.com/openai/codex) (required for historical environment reproduction)
- Java and Maven distributions (prepared by the toolchain setup script for reproduction)

## Installation

Clone RAVen and install its Python dependencies:

```bash
git clone https://github.com/riqueufmg/raven.git
cd raven
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

1. Download and configure DesigniteJava and RefactoringMiner. The expected locations are:

   ```text
   tools/DesigniteJava.jar
   tools/RefactoringMiner-3.0.7/
   ```

   DesigniteJava requires its own license. Third-party binaries and license files are not included in this repository.

2. Edit `config/raven.yml` to select the repository, branch, analysis period, and smells. For example:

   ```yaml
   repository:
     url: https://github.com/javaparser/javaparser.git
     branch: master

   analysis:
     since: "01-01-2026"
     smells: [IM, HM, GC, UD]
   ```

   Keep the `paths` and other existing settings in `config/raven.yml`; the example above shows only the values most users need to change. You can also set these options on the Discovery page.

3. To reproduce historical commits, install and authenticate Codex CLI, then prepare the local Java and Maven toolchains:

   ```bash
   bash prepare_toolchains.sh
   ```

## Run RAVen

Start the web interface from the repository root:

```bash
bash raven.sh
```

Open **http://127.0.0.1:8501** in your browser. If RAVen runs on a remote server, use SSH port forwarding to access this address.

The interface provides four pages:

- **Discovery:** analyze a repository and find smell-removal candidates.
- **Jobs:** monitor ongoing discovery and reproduction tasks.
- **Candidates:** inspect validated candidates and select commits for reproduction.
- **Results:** review candidates and reproduction outcomes.

## Command-line interface

RAVen can also be used without the web interface:

```bash
python -m cli.main --help
python -m cli.main discover --config config/raven.yml
python -m cli.main status
python -m cli.main reproduce --config config/raven.yml
```

Discovery identifies candidates; reproduction reconstructs and validates the Maven build environment for a selected historical commit. Only Maven-based Java projects are supported for environment reproduction.
