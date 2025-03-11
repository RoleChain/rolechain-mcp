import json
from textwrap import dedent
from typing import Dict, Iterator, Optional
from dotenv import load_dotenv
import os
import re

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.storage.workflow.sqlite import SqliteWorkflowStorage
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.newspaper4k import Newspaper4kTools
from agno.utils.log import logger
from agno.utils.pprint import pprint_run_response
from agno.workflow import RunEvent, RunResponse, Workflow
from pydantic import BaseModel, Field

load_dotenv()

class NewsArticle(BaseModel):
    title: str = Field(..., description="Title of the article.")
    url: str = Field(..., description="Link to the article.")
    summary: Optional[str] = Field(
        ..., description="Summary of the article if available."
    )


class SearchResults(BaseModel):
    articles: list[NewsArticle]


class ScrapedArticle(BaseModel):
    title: str = Field(..., description="Title of the article.")
    url: str = Field(..., description="Link to the article.")
    summary: Optional[str] = Field(
        ..., description="Summary of the article if available."
    )
    content: Optional[str] = Field(
        ...,
        description="Full article content in markdown format. None if content is unavailable.",
    )
    nlp_keywords: list[str] = Field(
        ...,
        description="List of top ranked keywords extracted from the article.",
    )


class OutlineSection(BaseModel):
    title: str = Field(..., description="Section title")
    description: str = Field(..., description="Detailed description of what this section should cover")
    subsections: list[str] = Field(default_factory=list, description="List of subsection topics")

class BlogOutline(BaseModel):
    title: str = Field(..., description="The main title/headline of the blog post")
    sections: list[OutlineSection] = Field(..., description="List of main sections in the outline")


class BlogPostGenerator(Workflow):
    """Advanced workflow for generating professional blog posts with proper research and citations."""

    description: str = dedent("""\
    An intelligent blog post generator that creates engaging, well-researched content.
    This workflow orchestrates multiple AI agents to research, analyze, and craft
    compelling blog posts that combine journalistic rigor with engaging storytelling.
    The system excels at creating content that is both informative and optimized for
    digital consumption.
    """)

    # Search Agent: Handles intelligent web searching and source gathering
    searcher: Agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini"),
        tools=[DuckDuckGoTools()],
        description=dedent("""\
        You are BlogResearch-X, an elite research assistant specializing in discovering
        high-quality sources for compelling blog content. Your expertise includes:

        - Finding authoritative and trending sources
        - Evaluating content credibility and relevance
        - Identifying diverse perspectives and expert opinions
        - Discovering unique angles and insights
        - Ensuring comprehensive topic coverage\
        """),
        instructions=(
            "1. Search Strategy 🔍\n"
            "   - Find 10-15 relevant sources and select the 5-7 best ones\n"
            "   - Prioritize recent, authoritative content\n"
            "   - Look for unique angles and expert insights\n"
            "2. Source Evaluation 📊\n"
            "   - Verify source credibility and expertise\n"
            "   - Check publication dates for timeliness\n"
            "   - Assess content depth and uniqueness\n"
            "3. Diversity of Perspectives 🌐\n"
            "   - Include different viewpoints\n"
            "   - Gather both mainstream and expert opinions\n"
            "   - Find supporting data and statistics"
        ),
        response_model=SearchResults,
        structured_outputs=True,
    )

    # Content Scraper: Extracts and processes article content
    article_scraper: Agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini"),
        tools=[Newspaper4kTools()],
        description=dedent("""\
        You are ContentBot-X, a specialist in extracting and processing digital content
        for blog creation. Your expertise includes:

        - Efficient content extraction
        - Smart formatting and structuring
        - Key information identification
        - Quote and statistic preservation
        - Maintaining source attribution\
        """),
        instructions=(
            "1. Content Extraction 📑\n"
            "   - Extract content from the article\n"
            "   - Preserve important quotes and statistics\n"
            "   - Maintain proper attribution\n"
            "   - Handle paywalls gracefully\n"
            "2. Content Processing 🔄\n"
            "   - Format text in clean markdown\n"
            "   - Preserve key information\n"
            "   - Structure content logically\n"
            "3. Quality Control ✅\n"
            "   - Verify content relevance\n"
            "   - Ensure accurate extraction\n"
            "   - Maintain readability"
        ),
        response_model=ScrapedArticle,
        structured_outputs=True,
    )

    # Content Writer Agent: Crafts engaging blog posts from research
    writer: Agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        description=dedent("""\
        You are BlogMaster-X, a skilled content creator who writes in a clear, engaging, 
        and conversational style. Your strengths include:

        - Writing in simple, easy-to-understand language
        - Directly addressing and connecting with readers
        - Breaking complex topics into digestible chunks
        - Using short, clear sentences (15-20 words on average)
        - Creating practical, detailed content with real examples
        - Maintaining a friendly, expert tone throughout
        - Using modern, natural transitions between ideas
        """),
        instructions=dedent("""\
        1. Writing Style Guidelines 📝
           - Use simple, clear language (aim for 8th-grade reading level)
           - Write short, direct sentences
           - Break up long paragraphs (3-4 sentences max)
           - Address readers directly using "you" and "your"
           - Avoid jargon and complex terminology
           - Use natural transitions instead of formal ones
           
        2. Content Structure 🏗️
           - Start sections with a clear topic sentence
           - Include specific examples and details
           - Use bullet points for lists
           - Add subheadings for better navigation
           - Maintain logical flow between ideas
           
        3. Engagement Techniques 🎯
           - Write like you're explaining to a friend
           - Include practical, actionable advice
           - Use relevant examples from daily life
           - Add mini-summaries for complex points
           - Incorporate reader questions/concerns
           
        4. Technical Content Guidelines 📊
           - Explain specifications in plain language
           - Compare features using real-world impact
           - Include specific performance details
           - Explain why recommendations matter
           - Use concrete examples for abstract concepts
        """),
        expected_output=dedent("""\
        ## {Clear, Benefit-Focused Section Title}
        
        {Easy-to-read content with short paragraphs}
        {Specific examples and practical details}
        {Direct reader address and conversational tone}
        {Clear explanations of technical concepts}
        {Natural transitions between ideas}
        """),
        markdown=True,
    )

    # Outline Creator Agent: Creates optimized content outline
    outline_creator: Agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        description=dedent("""\
        You are OutlineMaster-X, an expert at creating comprehensive, well-structured blog post outlines.
        Your expertise includes:
        
        - Creating engaging, viral-worthy headlines
        - Breaking complex topics into logical sections
        - Ensuring comprehensive topic coverage
        - Optimizing content flow and structure
        - Planning for 5000+ word articles
        - Identifying key angles and perspectives to cover
        
        Note: Do not include introduction, conclusion, or FAQ sections - these will be handled separately.
        Focus only on the main content sections of the blog post.
        """),
        instructions=dedent("""\
        1. Outline Strategy 📋
           - Create a compelling main headline
           - Design 6-8 main content sections
           - Include 3-5 subsections per main section
           - Ensure logical flow between sections
           - Plan for extensive content coverage
           - Do not include intro/conclusion/FAQ sections
           
        2. Section Planning 🎯
           - Write detailed descriptions for each section
           - Include key points to cover
           - Specify research areas and angles
           - Note important examples or case studies to include
           
        3. Content Depth 📚
           - Plan for 200-300 words per main section
           - Ensure comprehensive topic coverage
           - Include practical and theoretical aspects
           - Balance information density with readability
        """),
        response_model=BlogOutline,
        structured_outputs=True,
    )

    # Viral Intro Creator Agent: Creates attention-grabbing intros
    viral_intro_creator: Agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        description=dedent("""\
        You are ViralIntro-X, an expert at writing engaging, reader-friendly introductions
        that hook readers immediately. Your expertise includes:
        
        - Writing clear, conversational opening paragraphs
        - Creating personal connections with readers
        - Using simple language that everyone understands
        - Asking thought-provoking questions
        - Telling relatable mini-stories
        - Making complex topics approachable
        """),
        instructions=dedent("""\
        Important: Do not include any heading markers (#) in your output. The title is handled separately.
        
        1. Opening Strategy 🎯
           - Start with a relatable situation or question
           - Use simple, everyday language
           - Address the reader directly
           - Create an "aha" moment or curiosity
           - Keep sentences short and punchy
           
        2. Introduction Structure 📝
           - Begin with a hook (question/story/fact)
           - Connect to reader's daily life
           - Present the main problem/challenge
           - Promise clear, practical solutions
           - Keep paragraphs short (2-3 sentences)
           
        3. Engagement Elements ⚡
           - Use conversational tone throughout
           - Include "you" and "your" frequently
           - Share relevant personal angles
           - Ask engaging questions
           - Preview practical benefits
           
        4. Language Guidelines 📖
           - Aim for 8th-grade reading level
           - Use active voice
           - Avoid jargon and complex words
           - Write like you're talking to a friend
           - Keep sentences under 20 words
           
        5. Formatting Requirements 📋
           - Do not include any markdown headings
           - Start directly with the engaging content
           - Use regular paragraphs only
        """),
        markdown=True,
    )

    # Conclusion Creator Agent: Creates impactful conclusions
    conclusion_creator: Agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        description=dedent("""\
        You are ConclusionMaster-X, an expert at writing powerful, memorable conclusions 
        that reinforce key points and inspire action. Your expertise includes:
        
        - Summarizing key takeaways effectively
        - Creating strong calls to action
        - Reinforcing the value proposition
        - Connecting back to the introduction
        - Leaving readers with actionable insights
        - Making memorable final impressions
        """),
        instructions=dedent("""\
        1. Conclusion Strategy 🎯
           - Summarize main points concisely
           - Reinforce the core message
           - Connect back to the opening hook
           - Provide clear next steps
           - End with impact
           
        2. Structure Guidelines 📝
           - Start with a transition
           - Recap key insights (3-5 points)
           - Add value-focused takeaways
           - Include specific action items
           - Close with memorable statement
           
        3. Engagement Elements ⚡
           - Use confident, inspiring tone
           - Keep paragraphs short and punchy
           - Include forward-looking statements
           - Address reader's journey
           - End with momentum
        """),
        markdown=True,
    )

    # FAQ Creator Agent: Creates comprehensive FAQ sections
    faq_creator: Agent = Agent(
        model=OpenAIChat(id="gpt-4o"),
        description=dedent("""\
        You are FAQMaster-X, an expert at creating comprehensive, valuable FAQ sections
        that address reader concerns and add depth to content. Your expertise includes:
        
        - Anticipating reader questions
        - Providing clear, concise answers
        - Addressing common misconceptions
        - Adding valuable supplementary information
        - Maintaining consistent tone and style
        """),
        instructions=dedent("""\
        1. FAQ Development Strategy 🤔
           - Identify core reader concerns
           - Address common misconceptions
           - Cover practical implementation
           - Include expert insights
           - Add value beyond main content
           
        2. Question Guidelines 📝
           - Write clear, specific questions
           - Use reader's language
           - Focus on actionable concerns
           - Include both basic and advanced topics
           - Maintain logical progression
           
        3. Answer Structure ✨
           - Provide direct, complete answers
           - Include specific examples
           - Keep responses concise
           - Add relevant context
           - Link to main content where appropriate
           
        4. Format Requirements 📋
           - Use H2 for "Frequently Asked Questions"
           - Format questions as H3
           - Write clear paragraph answers
           - Maintain consistent structure
           - Ensure proper markdown formatting
        """),
        markdown=True,
    )

    def run(
        self,
        topic: str,
        use_search_cache: bool = True,
        use_scrape_cache: bool = True,
        use_cached_report: bool = True,
    ) -> Iterator[RunResponse]:
        logger.info(f"Generating a blog post on: {topic}")

        # Use the cached blog post if use_cache is True
        if use_cached_report:
            cached_blog_post = self.get_cached_blog_post(topic)
            if cached_blog_post:
                yield RunResponse(
                    content=cached_blog_post, event=RunEvent.workflow_completed
                )
                return

        # Search the web for articles on the topic
        search_results: Optional[SearchResults] = self.get_search_results(
            topic, use_search_cache
        )
        # If no search_results are found for the topic, end the workflow
        if search_results is None or len(search_results.articles) == 0:
            yield RunResponse(
                event=RunEvent.workflow_completed,
                content=f"Sorry, could not find any articles on the topic: {topic}",
            )
            return

        # Scrape the search results
        scraped_articles: Dict[str, ScrapedArticle] = self.scrape_articles(
            search_results, 
            use_scrape_cache,
            topic
        )

        # Write a blog post
        yield from self.write_blog_post(topic, scraped_articles)

    def get_cached_blog_post(self, topic: str) -> Optional[str]:
        logger.info("Checking if cached blog post exists")
        return self.session_state.get("blog_posts", {}).get(topic)

    def add_blog_post_to_cache(self, topic: str, blog_post: str):
        logger.info(f"Saving blog post for topic: {topic}")
        self.session_state.setdefault("blog_posts", {})
        self.session_state["blog_posts"][topic] = blog_post
        # Save the blog post to the storage
        self.write_to_storage()

    def get_cached_search_results(self, topic: str) -> Optional[SearchResults]:
        logger.info("Checking if cached search results exist")
        return self.session_state.get("search_results", {}).get(topic)

    def add_search_results_to_cache(self, topic: str, search_results: SearchResults):
        logger.info(f"Saving search results for topic: {topic}")
        self.session_state.setdefault("search_results", {})
        self.session_state["search_results"][topic] = search_results.model_dump()
        # Save the search results to the storage
        self.write_to_storage()

    def get_cached_scraped_articles(
        self, topic: str
    ) -> Optional[Dict[str, ScrapedArticle]]:
        logger.info("Checking if cached scraped articles exist")
        return self.session_state.get("scraped_articles", {}).get(topic)

    def add_scraped_articles_to_cache(
        self, topic: str, scraped_articles: Dict[str, ScrapedArticle]
    ):
        logger.info(f"Saving scraped articles for topic: {topic}")
        self.session_state.setdefault("scraped_articles", {})
        self.session_state["scraped_articles"][topic] = scraped_articles
        # Save the scraped articles to the storage
        self.write_to_storage()

    def get_search_results(
        self, topic: str, use_search_cache: bool, num_attempts: int = 3
    ) -> Optional[SearchResults]:
        # Get cached search_results from the session state if use_search_cache is True
        if use_search_cache:
            try:
                search_results_from_cache = self.get_cached_search_results(topic)
                if search_results_from_cache is not None:
                    search_results = SearchResults.model_validate(
                        search_results_from_cache
                    )
                    logger.info(
                        f"Found {len(search_results.articles)} articles in cache."
                    )
                    return search_results
            except Exception as e:
                logger.warning(f"Could not read search results from cache: {e}")

        # If there are no cached search_results, use the searcher to find the latest articles
        for attempt in range(num_attempts):
            try:
                searcher_response: RunResponse = self.searcher.run(topic)
                if (
                    searcher_response is not None
                    and searcher_response.content is not None
                    and isinstance(searcher_response.content, SearchResults)
                ):
                    article_count = len(searcher_response.content.articles)
                    logger.info(
                        f"Found {article_count} articles on attempt {attempt + 1}"
                    )
                    # Cache the search results
                    self.add_search_results_to_cache(topic, searcher_response.content)
                    return searcher_response.content
                else:
                    logger.warning(
                        f"Attempt {attempt + 1}/{num_attempts} failed: Invalid response type"
                    )
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{num_attempts} failed: {str(e)}")

        logger.error(f"Failed to get search results after {num_attempts} attempts")
        return None

    def scrape_articles(
        self, 
        search_results: SearchResults, 
        use_scrape_cache: bool,
        topic: str
    ) -> Dict[str, ScrapedArticle]:
        scraped_articles: Dict[str, ScrapedArticle] = {}

        # Get cached scraped_articles from the session state if use_scrape_cache is True
        if use_scrape_cache:
            try:
                scraped_articles_from_cache = self.get_cached_scraped_articles(topic)
                if scraped_articles_from_cache is not None:
                    scraped_articles = scraped_articles_from_cache
                    logger.info(
                        f"Found {len(scraped_articles)} scraped articles in cache."
                    )
                    return scraped_articles
            except Exception as e:
                logger.warning(f"Could not read scraped articles from cache: {e}")

        # Scrape the articles that are not in the cache
        for article in search_results.articles:
            if article.url in scraped_articles:
                logger.info(f"Found scraped article in cache: {article.url}")
                continue

            article_scraper_response: RunResponse = self.article_scraper.run(
                article.url
            )
            if (
                article_scraper_response is not None
                and article_scraper_response.content is not None
                and isinstance(article_scraper_response.content, ScrapedArticle)
            ):
                scraped_articles[article_scraper_response.content.url] = (
                    article_scraper_response.content
                )
                logger.info(f"Scraped article: {article_scraper_response.content.url}")

        # Save the scraped articles in the session state
        self.add_scraped_articles_to_cache(topic, scraped_articles)
        return scraped_articles

    def write_section(self, section: OutlineSection, topic: str, scraped_articles: Dict[str, ScrapedArticle], outline: BlogOutline, written_sections: str = "") -> str:
        """Write a single section of the blog post with awareness of the full outline and previous content"""
        logger.info(f"Writing section: {section.title}")
        
        writer_input = {
            "topic": topic,
            "current_section": section.model_dump(),
            "full_outline": outline.model_dump(),
            "previously_written_content": written_sections,
            "articles": [
                v if isinstance(v, dict) else v.model_dump() 
                for v in scraped_articles.values()
            ],
        }
        
        response = self.writer.run(json.dumps(writer_input, indent=4))
        return response.content if response and response.content else ""

    def get_next_blog_number(self) -> int:
        """Get the next blog number by checking existing files in blogOutputs folder"""
        blog_dir = "blogOutputs"
        # Create directory if it doesn't exist
        os.makedirs(blog_dir, exist_ok=True)
        
        # List all files and filter for example*.md pattern
        files = [f for f in os.listdir(blog_dir) if f.startswith("example") and f.endswith(".md")]
        
        if not files:
            return 1
            
        # Extract numbers and find the highest
        numbers = [int(re.search(r'example(\d+)\.md', f).group(1)) for f in files]
        return max(numbers) + 1

    def format_blog_content(self, content: str) -> str:
        """Format the blog content with proper markdown and spacing"""
        # Add any additional formatting here if needed
        # Currently the content should already be properly formatted 
        # since we're using markdown=True in our agents
        return content

    def save_blog_to_file(self, content: str):
        """Save the formatted blog content to the next numbered file"""
        next_number = self.get_next_blog_number()
        filename = f"example{next_number}.md"
        filepath = os.path.join("blogOutputs", filename)
        
        formatted_content = self.format_blog_content(content)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
            
        logger.info(f"Blog post saved to: {filepath}")

    def write_blog_post(
        self, topic: str, scraped_articles: Dict[str, ScrapedArticle]
    ) -> Iterator[RunResponse]:
        logger.info("Creating blog post outline")
        
        # Generate the outline
        outline_response = self.outline_creator.run(topic)
        if not outline_response or not outline_response.content:
            yield RunResponse(
                event=RunEvent.workflow_completed,
                content=f"Failed to create outline for topic: {topic}",
            )
            return

        outline: BlogOutline = outline_response.content
        
        # Start with the title
        full_post = f"# {outline.title}\n\n"
        
        # Generate viral intro
        logger.info("Creating viral introduction")
        intro_input = {
            "topic": topic,
            "outline": outline.model_dump(),
            "articles": [
                v if isinstance(v, dict) else v.model_dump() 
                for v in scraped_articles.values()
            ],
        }
        
        intro_response = self.viral_intro_creator.run(json.dumps(intro_input, indent=4))
        if intro_response and intro_response.content:
            full_post += f"{intro_response.content}\n\n"
            yield RunResponse(
                event=RunEvent.run_response,
                content="Completed viral introduction",
            )
        
        written_sections = full_post
        
        # Write each section
        for section in outline.sections:
            section_content = self.write_section(
                section, 
                topic, 
                scraped_articles,
                outline,
                written_sections
            )
            full_post += f"\n{section_content}\n"
            written_sections = full_post
            # Yield progress update
            yield RunResponse(
                event=RunEvent.run_response,
                content=f"Completed section: {section.title}",
            )

        # Generate conclusion (only once)
        logger.info("Creating conclusion")
        conclusion_input = {
            "topic": topic,
            "outline": outline.model_dump(),
            "full_content": written_sections,
            "articles": [
                v if isinstance(v, dict) else v.model_dump() 
                for v in scraped_articles.values()
            ],
        }
        
        conclusion_response = self.conclusion_creator.run(json.dumps(conclusion_input, indent=4))
        if conclusion_response and conclusion_response.content:
            # full_post += f"\n## Conclusion\n\n{conclusion_response.content}\n\n"
            full_post += f"\n\n{conclusion_response.content}\n\n"
            yield RunResponse(
                event=RunEvent.run_response,
                content="Completed conclusion",
            )

        # Generate FAQ section
        logger.info("Creating FAQ section")
        faq_input = {
            "topic": topic,
            "outline": outline.model_dump(),
            "full_content": full_post,
            "articles": [
                v if isinstance(v, dict) else v.model_dump() 
                for v in scraped_articles.values()
            ],
        }
        
        faq_response = self.faq_creator.run(json.dumps(faq_input, indent=4))
        if faq_response and faq_response.content:
            full_post += f"{faq_response.content}\n"
            yield RunResponse(
                event=RunEvent.run_response,
                content="Completed FAQ section",
            )

        # After generating the full post and before the final yield:
        try:
            self.save_blog_to_file(full_post)
        except Exception as e:
            logger.error(f"Failed to save blog post to file: {e}")

        # Final response with complete post
        yield RunResponse(
            event=RunEvent.workflow_completed,
            content=full_post,
        )
        
        # Save the blog post in the cache
        self.add_blog_post_to_cache(topic, full_post)


# Run the workflow if the script is executed directly
if __name__ == "__main__":
    import random

    from rich.prompt import Prompt

    # Fun example prompts to showcase the generator's versatility
    example_prompts = [
        "Why Cats Secretly Run the Internet",
        "The Science Behind Why Pizza Tastes Better at 2 AM",
        "Time Travelers' Guide to Modern Social Media",
        "How Rubber Ducks Revolutionized Software Development",
        "The Secret Society of Office Plants: A Survival Guide",
        "Why Dogs Think We're Bad at Smelling Things",
        "The Underground Economy of Coffee Shop WiFi Passwords",
        "A Historical Analysis of Dad Jokes Through the Ages",
    ]

    # Get topic from user
    topic = Prompt.ask(
        "[bold]Enter a blog post topic[/bold] (or press Enter for a random example)\n✨",
        default=random.choice(example_prompts),
    )

    # Convert the topic to a URL-safe string for use in session_id
    url_safe_topic = topic.lower().replace(" ", "-")

    # Initialize the blog post generator workflow
    # - Creates a unique session ID based on the topic
    # - Sets up SQLite storage for caching results
    generate_blog_post = BlogPostGenerator(
        session_id=f"generate-blog-post-on-{url_safe_topic}",
        storage=SqliteWorkflowStorage(
            table_name="generate_blog_post_workflows",
            db_file="tmp/workflows.db",
        ),
    )

    # Execute the workflow with caching enabled
    # Returns an iterator of RunResponse objects containing the generated content
    blog_post: Iterator[RunResponse] = generate_blog_post.run(
        topic=topic,
        use_search_cache=True,
        use_scrape_cache=True,
        use_cached_report=True,
    )

    # Print the response
    pprint_run_response(blog_post, markdown=True)
