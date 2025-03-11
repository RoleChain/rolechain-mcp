# AI Article Generator with Phidata

This repository contains a proof-of-concept implementation of an AI-powered article generation system using [Phidata](https://github.com/phidatahq/phidata) as the initial agent framework. The system aims to demonstrate automated blog post creation with intelligent web research and content generation capabilities.



## Setup Instructions

### Prerequisites
- .env file with OPENAI_API_KEY
- tmp folder to store the generated blog posts

### 1. Create Python Virtual Environment

First, create and activate a Python virtual environment:

```bash
# On macOS/Linux:
python3 -m venv venv
source venv/bin/activate

# On Windows:
python -m venv venv
venv\Scripts\activate
```

### 2. Install Required Packages

Install all required packages from requirements.txt:

```bash
# On macOS/Linux:
pip3 install -r requirements

# On Windows:
pip install -r requirements.txt
```

### 3. Run python file

```bash
# On macOS/Linux:
python3 blog_post_generator.py

# On Windows:
python blog_post_generator.py
```


### 4. Generated Blog Posts

After running the script, the generated blog post will be saved in the `blogOutputs` folder as `example{count}.md`, where `count` is an incremental number (1, 2, 3, etc.) based on existing files. For example:
- First generation: `example1.md`
- Second generation: `example2.md` 
- And so on...

You can find all your generated blog posts in the `tmp` directory, with each new generation getting the next available number in sequence.





