# **RAVen** - <u>R</u>eal-world <u>A</u>utomated <u>V</u>alidation of R<u>e</u>factori<u>n</u>gs

Tool for reproducing historical Java/Maven project environments.

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

## Usage

To reproduce a historical commit:

```bash
python repro.py \
  --repo https://github.com/example/project.git \
  --commit <commit-sha>
```

JaCoRE attempts to reconstruct a build environment for the target commit without modifying tracked project files.

## Output

Each reproduction is stored under:

```text
benchmark/repositories/<repository>/commits/<commit>/
```

The generated environment may include:

```text
m2/               isolated Maven repository
dependency-src/   reconstructed dependency sources, when required
logs/             reproduction logs
manifest.txt      reproduction status and metadata
reproduce.sh      executable reproduction script
settings.xml      Maven settings, when required
```

## Validation

A reproduction is considered successful only when the generated environment can execute:

```bash
mvn -o clean test
```

successfully using the isolated dependencies and the selected local toolchains.

## Scope

JaCoRE currently targets historical Java projects built with Maven.

The tool reconstructs the build environment of a historical commit. It does not modify tracked source files, tests, POM files, or build configuration to make a failing project pass.