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
        and *very* conversational style. Your strengths include:
        - Using short, direct sentences (10-15 words max).
        - Writing at or below an 8th-grade reading level.
        - Explaining technical or detailed topics with plenty of examples.
        - Avoiding fluff, repetition, or obvious filler lines.
        - Using simple, modern language without outdated or formal transitions.
        - Directly addressing the reader with “you” and “your.”
        - Expanding on product or feature recommendations with real benefits, specs, and use cases.
        - Maintaining a warm, friendly, and expert tone throughout.
        """),
        instructions=dedent("""\
        1. Writing Style Guidelines 📝
           - Keep sentences under 15 words.
           - Use plain, everyday words (avoid 'intricacies', 'transcended', 'delve', 'moreover', etc.).
           - Avoid fluff or repeating what the heading already states.
           - Talk directly to the reader with “you” and “your.”
           - Keep paragraphs 2-4 sentences each for easy scanning.

        2. Content Depth & Clarity 🏗
           - Provide genuinely helpful details: if you mention a product or feature, share its specs and real-world benefits.
           - Walk readers through steps with practical examples in how-to sections.
           - Prioritize clarity over formality or complexity.
           - If citing a statistic or fact, briefly mention its source (e.g., “according to [source name]”).

        3. Engagement & Friendliness 🎯
           - Write like a sincere friend or knowledgeable expert.
           - Ask rhetorical questions or mention common doubts.
           - Use transitions like “Also,” or “Another thing...” instead of formal words like “moreover.”
           - Avoid passive constructions; keep language direct and active.

        4. Tone & Word Choice ⚡
           - Never use AI-sounding phrases like “in the realm of…” or “the ever-evolving world of…”
           - Stick to second person (“you,” “your”) as much as possible.
           - Keep paragraphs short (2-4 sentences) and straightforward.
           - Omit filler lines like “Ensuring X is vital” unless you explain exactly *why*.

        5. Specific Structure 🧩
           - Treat each section as a mini-topic. Start with a concise lead-in sentence.
           - Use your main keyword near the front of the title; open with a concise hook that addresses the user’s immediate query.
           - Use bullet points where it helps clarity.
           - Add at least one example or practical tip per section.
           - Summarize the main idea if it helps reinforce a key concept.

        6. SEO & Source Attribution 🔎
           - Naturally integrate relevant keywords without “stuffing.”
           - Reference credible sources or stats in parentheses or short mentions if they add value.
           - Maintain readability above all else.
                            
        """),
        expected_output=dedent("""\
        ## {Clear, Benefit-Focused Section Title}

        {Easy-to-read content with short paragraphs}
        {Specific examples and practical details}
        {Direct reader address and conversational tone}
        {Clear explanations of technical concepts}
        {Natural transitions using modern language}
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
        """),
        instructions=dedent("""\
        1. Outline Strategy 📋
           - Create a compelling main headline
           - Design 6-8 main content sections
           - Include 3-5 subsections per main section
           - Ensure logical flow between sections
           - Plan for extensive content coverage (up to 5000 words total)
           - Do not include intro/conclusion/FAQ sections (other agents handle those)
           
        2. Section Planning 🎯
           - Write detailed descriptions for each section
           - Include key points to cover, highlighting deeper explorations (e.g., full specs, real-life scenarios)
           - Mention any important examples or case studies to integrate
           - Indicate where more depth or comparisons might be needed
           
        3. Content Depth 📚
           - Plan for at least 200-300 words per main section
           - Provide hints for real-world examples
           - Balance technical details with easy readability
           - Make sure the writer can naturally expand to practical, helpful details
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
           - Start with a short, relatable question or statement
           - Use everyday words (avoid "ever-evolving," "realm," "delve," etc.)
           - Directly address the reader with “you” and “your”
           - Keep sentences short and punchy

        2. Introduction Structure 📝
           - Hook the reader with a question/story/fact they can relate to
           - Connect to the reader’s daily life or aspirations
           - Present the main problem/challenge or curiosity
           - Promise clear, practical solutions
           - Keep paragraphs short (2-3 sentences each)

        3. Engagement Elements ⚡
           - Maintain a friendly, personal tone
           - Focus on what the reader cares about
           - Aim for 10-15 words per sentence, max
           - Use “Also,” “Plus,” or “One more thing…” for transitions when needed

        4. Language Guidelines 📖
           - Write at an 8th-grade reading level
           - Use active voice and second person
           - Avoid filler or fluff

        5. Formatting Requirements 📋
           - No markdown headings
           - No bullet points in the intro (keep it short, direct paragraphs)
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
           - Summarize main points briefly (3-5 quick references)
           - Reinforce the core message and benefits
           - Include a clear call to action or next step
           - End on a short, punchy statement that resonates
           
        2. Structure Guidelines 📝
           - Start with a light transition (e.g., “Let’s wrap things up…”)
           - Recap 3-5 big insights from the post
           - Connect back to the intro’s hook if possible
           - Keep paragraphs short (2-3 sentences)
           
        3. Engagement Elements ⚡
           - Maintain a friendly, encouraging tone
           - Use second person: “you,” “your next step”
           - Ask a final question or give a motivational push
           
        4. Style & Language 📋
           - Avoid AI-sounding, formal phrases like “in summary,” “ultimately,” “in the realm of…”
           - Stick to modern, plain English
           - Sentence length: under 15 words each
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
           - Identify common reader concerns or misunderstandings
           - Include both beginner and slightly more advanced questions
           - Focus on how each answer can be practically helpful
           - Cover any leftover details the main article might have missed

        2. Question Guidelines 📝
           - Write clear, specific questions in second person: “Can you...?” “Do you need...?”
           - Avoid fluff or outdated transitions in questions
           - Keep them short and easy to skim
           
        3. Answer Structure ✨
           - Provide concise, direct answers in 2-4 sentences
           - Reference real examples or data if needed
           - Maintain a friendly, encouraging tone
           - Keep language at or below 8th-grade reading level

        4. Format Requirements 📋
           - Use H2 for "Frequently Asked Questions"
           - Format each question as H3
           - Provide short paragraph answers (2-4 sentences)
           - Avoid AI-sounding phrases or filler
           - Keep it straightforward and user-friendly
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
        if search_results is None or len(search_results.articles) == 0:
            yield RunResponse(
                event=RunEvent.workflow_completed,
                content=f"Sorry, could not find any articles on the topic: {topic}",
            )
            return

        # Scrape the search results
        scraped_articles: Dict[str, ScrapedArticle] = self.scrape_articles(
            search_results, use_scrape_cache
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
        self.write_to_storage()

    def get_cached_search_results(self, topic: str) -> Optional[SearchResults]:
        logger.info("Checking if cached search results exist")
        return self.session_state.get("search_results", {}).get(topic)

    def add_search_results_to_cache(self, topic: str, search_results: SearchResults):
        logger.info(f"Saving search results for topic: {topic}")
        self.session_state.setdefault("search_results", {})
        self.session_state["search_results"][topic] = search_results.model_dump()
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
        self.write_to_storage()

    def get_search_results(
        self, topic: str, use_search_cache: bool, num_attempts: int = 3
    ) -> Optional[SearchResults]:
        # Get cached search_results from the session state if use_search_cache is True
        if use_search_cache:
            try:
                search_results_from_cache = self.get_cached_search_results(topic)
                if search_results_from_cache is not None:
                    search_results = SearchResults.model_validate(search_results_from_cache)
                    logger.info(
                        f"Found {len(search_results.articles)} articles in cache."
                    )
                    return search_results
            except Exception as e:
                logger.warning(f"Could not read search results from cache: {e}")

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
        self, search_results: SearchResults, use_scrape_cache: bool
    ) -> Dict[str, ScrapedArticle]:
        scraped_articles: Dict[str, ScrapedArticle] = {}

        # If you need the 'topic' here for caching, pass it down from run() as an argument:
        topic = ""

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

        for article in search_results.articles:
            if article.url in scraped_articles:
                logger.info(f"Found scraped article in cache: {article.url}")
                continue

            article_scraper_response: RunResponse = self.article_scraper.run(article.url)
            if (
                article_scraper_response is not None
                and article_scraper_response.content is not None
                and isinstance(article_scraper_response.content, ScrapedArticle)
            ):
                scraped_articles[article_scraper_response.content.url] = article_scraper_response.content
                logger.info(f"Scraped article: {article_scraper_response.content.url}")

        # Store them under the correct topic
        self.add_scraped_articles_to_cache(topic, scraped_articles)
        return scraped_articles

    def write_section(
        self, 
        section: OutlineSection, 
        topic: str, 
        scraped_articles: Dict[str, ScrapedArticle],
        outline: BlogOutline, 
        written_sections: str = ""
    ) -> str:
        """Write a single section of the blog post with awareness of the full outline and previous content."""
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
        """Get the next blog number by checking existing files in blogOutputs folder."""
        blog_dir = "blogOutputs"
        os.makedirs(blog_dir, exist_ok=True)
        
        files = [f for f in os.listdir(blog_dir) if f.startswith("example") and f.endswith(".md")]
        
        if not files:
            return 1
            
        numbers = [int(re.search(r'example(\d+)\.md', f).group(1)) for f in files]
        return max(numbers) + 1

    def format_blog_content(self, content: str) -> str:
        """Format the blog content with proper markdown and spacing."""
        return content  # Additional formatting can be done here if needed

    def save_blog_to_file(self, content: str):
        """Save the formatted blog content to the next numbered file."""
        next_number = self.get_next_blog_number()
        filename = f"example{next_number}.md"
        filepath = os.path.join("blogOutputs", filename)
        
        formatted_content = self.format_blog_content(content)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
            
        logger.info(f"Blog post saved to: {filepath}")

    def write_blog_post(
        self, 
        topic: str, 
        scraped_articles: Dict[str, ScrapedArticle]
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
            
            yield RunResponse(
                event=RunEvent.run_response,
                content=f"Completed section: {section.title}",
            )

        # Generate conclusion
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
            # Add the conclusion below the last section
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

        # Save final post to file
        try:
            self.save_blog_to_file(full_post)
        except Exception as e:
            logger.error(f"Failed to save blog post to file: {e}")

        yield RunResponse(
            event=RunEvent.workflow_completed,
            content=full_post,
        )
        
        # Save the blog post in the cache
        self.add_blog_post_to_cache(topic, full_post)


# Run the workflow if script is executed directly
if __name__ == "__main__":
    import random
    from rich.prompt import Prompt

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

    topic = Prompt.ask(
        "[bold]Enter a blog post topic[/bold] (or press Enter for a random example)\n✨",
        default=random.choice(example_prompts),
    )

    url_safe_topic = topic.lower().replace(" ", "-")

    generate_blog_post = BlogPostGenerator(
        session_id=f"generate-blog-post-on-{url_safe_topic}",
        storage=SqliteWorkflowStorage(
            table_name="generate_blog_post_workflows",
            db_file="tmp/workflows.db",
        ),
    )

    blog_post: Iterator[RunResponse] = generate_blog_post.run(
        topic=topic,
        use_search_cache=True,
        use_scrape_cache=True,
        use_cached_report=True,
    )

    pprint_run_response(blog_post, markdown=True)
