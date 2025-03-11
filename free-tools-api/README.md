# Yotube MCP

## Tech Stack

**Server:** FastAPI, Python, Docker, Google Cloud Run

**Notable Dependencies:** ffmpeg, pydub, moviepy

# Guidelines for using docker locally

### Install Docker

### Build a docker image

To build **<image-name>** from current directory

```shell
    docker build -t <image-name> .
```

**Example:** To build a image named **tools-api** from current directory

```shell
    docker build -t tools-api .
```

### Run a docker image

To run the <image-name> image with host port 8080, container port 5000, and environment variables from a .env file:

```shell
    docker run --env-file <path-to-env-file> -p 8080:5000 <image-name>
```

**Example:** To run an image named tools-api with host port 8080, container port 5000, and environment variables from a .env file located in the project root:

```shell
    docker run --env-file ./.env -p 8080:5000 tools-api
```

**-p 8080:5000:** This flag maps the host port (8080) to the container port (5000). It means that any traffic coming into the host on port 8080 will be forwarded to the container on port 5000.

# 6 steps to deploy Docker on Google Cloud Run

- Create Repo
- Build Image
- Authorize Docker
- Tag Image
- Push Image
- Deploy on Cloud run

### Details of deployment

#### **1. Create Repo**

```shell
    No need to do so, as we already have a repo
```

---

#### **2. Build a docker image**

To build **<image-name>** from current directory

```shell
    docker build -t <image-name> .
```

**Example:** To build a image named **tools-api** from current directory

```shell
    docker build -t tools-api .
```

---

#### **3. Authorize Docker**

Authorize Docker in google cloud, gcloud and development machine

---

#### **4. Tag Image**

To tag **<image-name>** for the repo

```shell
    docker tag <image-name> <region>-docker.pkg.dev/<project-id>/<repository-name>/<image-name>
```
xw

Check if tagged correctly (Optional)

```bash
  docker image ls
```

---

#### **5. Push Image**

To push **<image-name>** for our repo

xw
#### **6. Deploy**

Go to the designated service url in google cloud console and deploy

```shell
    Click on Edit & Deploy New Revision and proceed
```xw
