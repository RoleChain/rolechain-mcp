from dotenv import load_dotenv
import os
import json
from typing import Optional, Iterator

from pydantic import BaseModel, Field

from phi.agent import Agent
from phi.workflow import Workflow, RunResponse, RunEvent
from phi.storage.workflow.sqlite import SqlWorkflowStorage
from phi.tools.duckduckgo import DuckDuckGo
from phi.utils.pprint import pprint_run_response
from phi.utils.log import logger

# Load environment variables from .env file
load_dotenv()

class TopArticle(BaseModel):
    title: str = Field(..., description="Title of the blog.")
    content_quality: str = Field(..., description="Content quality of the blog.")
    writing_style: str = Field(..., description="Writing style of the blog.")
    main_ideas_and_concepts: str = Field(..., description="Main ideas and concepts of the blog.")


class SearchResults(BaseModel):
    articles: list[TopArticle]


# instructions=["Given a topic, search for 20 articles and return the 5 most relevant articles."],

class BlogPostGenerator(Workflow):
    searcher: Agent = Agent(
        tools=[DuckDuckGo()],
        instructions=["Given a topic, search for the top 5 articles and analyze them for a comprehensive blog review report."],
        response_model=SearchResults,
    )

    writer: Agent = Agent(
        instructions=[
            # Blog Title Generation
            "Analyze the topic and review reports to generate 10 SEO-optimized, attention-grabbing titles. Ensure the titles are engaging, use target keywords naturally, and follow best SEO practices for higher click-through rates.",
            # Meta Description Generation
            "Craft a concise and compelling meta description (150-160 characters) that incorporates primary keywords and encourages clicks. Focus on highlighting the blog's core value and solving user intent.",
            # Blog Introduction Generation
            "Write a captivating and informative introduction that hooks readers instantly. Address the search intent clearly while providing a brief preview of the blog's key insights and solutions.",
            # Blog Outline Generation
            "Create a comprehensive blog outline structured with relevant sections and subheaders. Incorporate target keywords and ensure the flow logically guides readers through the topic, improving readability and SEO.",
            # Key Takeaways Generation
            "Summarize the blog’s main points in under 200 words using 4-6 concise bullet points. Focus on delivering high-impact insights that give readers a quick overview of the entire content.",
            # Blog Content Generation (Section by Section)
            "Develop in-depth, engaging, and SEO-friendly content for each section. Use subheaders, lists, and examples for clarity, and follow E-E-A-T guidelines to build trust and authority.",
            # Blog Conclusion Generation
            "Write a persuasive conclusion that summarizes the blog and reinforces its key points. End with a strong call to action that encourages reader engagement or next steps.",
            # FAQs Generation
            "Generate 5-6 relevant FAQs addressing potential reader queries not covered in the blog. Provide concise, informative answers that naturally include SEO keywords for added search visibility."
        ],

    )

    def run(self, topic: str, use_cache: bool = True) -> Iterator[RunResponse]:
        logger.info(f"Generating a blog post on: {topic}")

        # Use the cached blog post if use_cache is True
        if use_cache and "blog_posts" in self.session_state:
            logger.info("Checking if cached blog post exists")
            for cached_blog_post in self.session_state["blog_posts"]:
                if cached_blog_post["topic"] == topic:
                    logger.info("Found cached blog post")
                    yield RunResponse(
                        run_id=self.run_id,
                        event=RunEvent.workflow_completed,
                        content=cached_blog_post["blog_post"],
                    )
                    return

        # Step 1: Search the web for articles on the topic
        num_tries = 0
        search_results: Optional[SearchResults] = None
        # Run until we get a valid search results
        while search_results is None and num_tries < 3:
            try:
                num_tries += 1
                searcher_response: RunResponse = self.searcher.run(topic)
                if (
                    searcher_response
                    and searcher_response.content
                    and isinstance(searcher_response.content, SearchResults)
                ):
                    logger.info(f"Searcher found {len(searcher_response.content.articles)} articles.")
                    search_results = searcher_response.content
                else:
                    logger.warning("Searcher response invalid, trying again...")
            except Exception as e:
                logger.warning(f"Error running searcher: {e}")

        # If no search_results are found for the topic, end the workflow
        if search_results is None or len(search_results.articles) == 0:
            yield RunResponse(
                run_id=self.run_id,
                event=RunEvent.workflow_completed,
                content=f"Sorry, could not find any articles on the topic: {topic}",
            )
            return

        # Step 2: Write a blog post
        logger.info("Writing blog post")
        # Prepare the input for the writer
        writer_input = {
            "topic": topic,
            "articles": [v.model_dump() for v in search_results.articles],
        }
        # Run the writer and yield the response
        yield from self.writer.run(json.dumps(writer_input, indent=4), stream=True)

        # Save the blog post in the session state for future runs
        if "blog_posts" not in self.session_state:
            self.session_state["blog_posts"] = []
        self.session_state["blog_posts"].append({"topic": topic, "blog_post": self.writer.run_response.content})


# The topic to generate a blog post on
topic = "Avoid Ai Detection"

# Create the workflow
generate_blog_post = BlogPostGenerator(
    session_id=f"generate-blog-post-on-{topic}",
    storage=SqlWorkflowStorage(
        table_name="generate_blog_post_workflows",
        db_file="tmp/workflows.db",
    ),
)

# Run workflow
blog_post: Iterator[RunResponse] = generate_blog_post.run(topic=topic, use_cache=True)

# Print the response
pprint_run_response(blog_post, markdown=True)
