Got it — your module folder is:

```
external-services/acctgateway/data-mesh/psdata/peoplesoft_data_archive_partitions
```

Everything I explained for *clean\_fy* applies 1-for-1 to this directory.
Below is the **exact set of files** and their paths under that folder.

```
peoplesoft_data_archive_partitions/          ← project root
│
├─ build.gradle
├─ requirements.txt
├─ Dockerfile.pre                ← optional (apt/yum installs)
├─ gradlew                       ← copy from repo root (or symlink/alias)
└─ gradle/
   └─ wrapper/
      ├─ gradle-wrapper.jar
      └─ gradle-wrapper.properties  (distributionUrl → Artifactory mirror)
└─ src/
   └─ main/
      └─ python/
         └─ psdata/
            ├─ delete_tables.py
            ├─ soft_archive.py
            └─ hard_delete.py   (or whatever helpers you already have)
```

---

### 1  `build.gradle`

```groovy
plugins {
    id 'citsource.common-conventions'   version '1.5.0'
    id 'citsource.python-conventions'   version '1.5.0'
    id 'com.citadel.cigdocker'          version '1.5.0'
}

python {
    srcDir = file('src/main/python')
}

cigdocker {
    createDockerImage = true

    imageName = 'psdata/lifecycle-retention'
    baseImage = 'artifactory.citadelgroup.com/docker-remote/python:3.12-slim'

    extraTags = ['soft', 'nonstop']
    includeServiceRouterSidecarRunner = false

    dockerPrependFile = file('Dockerfile.pre')        // comment out if not used
}
```

*(Change plugin versions if your Artifactory shows a newer stable `1.x`.)*

---

### 2  `requirements.txt`

```
google-cloud-storage==2.*
google-cloud-bigquery==3.*
typer==0.12.*
```

Add any other libs your scripts import.

---

### 3  `Dockerfile.pre` (optional)

```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*
```

Delete or leave empty if you don’t need extra OS packages.

---

### 4  Gradle wrapper (copy once)

```bash
# From the repo root:
cp gradlew external-services/acctgateway/data-mesh/psdata/peoplesoft_data_archive_partitions/
cp -r gradle/wrapper external-services/acctgateway/data-mesh/psdata/peoplesoft_data_archive_partitions/gradle/

# Make sure the URL is internal:
sed -i 's#services.gradle.org#artifactory.citadelgroup.com/gradle#' \
    external-services/.../gradle/wrapper/gradle-wrapper.properties
```

(Or use your alias that already points to the root wrapper.)

---

### 5  Local verification

```bash
# From the **monorepo root**:
./gradlew focus --project peoplesoft_data_archive_partitions dockerfile

# Optional local build:
external-services/acctgateway/data-mesh/psdata/peoplesoft_data_archive_partitions/build/Dockerfile.python.sh
```

You should see no proxy errors and a `BUILD SUCCESSFUL`.

---

### 6  CI behaviour

Every push triggers CDX to:

1. Detect `createDockerImage = true`.
2. Generate Dockerfile, merge `Dockerfile.pre`.
3. Build once, tag: `:soft` and `:nonstop`.
4. Push to
   `artifactory.citadelgroup.com/docker-dev-01-local/psdata/lifecycle-retention`.

Register those two tags in **Batch UI → Docker**, schedule your jobs, and you’re done.

**Nothing else is required**—the root `settings.gradle` auto-discovers the folder because it now contains a valid `build.gradle`.
