# Multi-Content Platform (MCP)

A comprehensive content management and generation platform combining media processing capabilities with AI-powered content creation.

## Core Components

### 1. Free Tools API (@free-tools-api)
A FastAPI-based service providing various content processing tools:
- **Video Processing**: Download and convert YouTube videos
- **Format Conversion**: Support for mp4, avi, mov, flv, mkv, webm, 3gp, mpeg
- **Audio Processing**: Extract audio and generate transcriptions
- **Background Processing**: Celery + Redis for handling heavy tasks
- **Process Management**: Supervisord integration

### 2. Agentic Article Generator (@Agentic-Article-Gen)
AI-powered blog post generation system built with Phidata:
- **Content Generation**: Automated blog post creation
- **Specialized Agents**: 
  - Content research and scraping
  - Outline creation
  - Conclusion writing
  - FAQ generation
- **Natural Language Processing**: Advanced text generation and refinement
- **Output Format**: Markdown-formatted blog posts

## Architecture

The platform is designed with:
- API-first approach for maximum flexibility
- Containerized services using Docker
- Background task processing for scalability
- Environment-based configuration
- Robust error handling

## Getting Started

1. Clone the repositories: