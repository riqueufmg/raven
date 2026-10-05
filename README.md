# **JaCoRE** - Java Commit Reproducibility Environment

Tool for reproducing historical Java/Maven project environments.

## Prepare toolchains

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