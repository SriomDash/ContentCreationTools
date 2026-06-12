import yaml
import os
from dotenv import load_dotenv
load_dotenv()

model_name = os.getenv('GOOGLE_MODEL_NAME')

if not model_name:
    raise ValueError("GOOGLE_MODEL is not set in the environment variables.")

from google.adk.agents.llm_agent import Agent
from .tools import (
    select_theme,
    generate_histogram,
    generate_pie_chart,
    generate_bar_chart,
    generate_multi_value_bar_chart,
    generate_line_chart,
    generate_multi_value_line_chart,
    generate_scatter_plot,
    generate_area_chart
)

# 1. Safely locate and load the prompt.yaml file
current_dir = os.path.dirname(os.path.abspath(__file__))
yaml_path = os.path.join(current_dir, 'prompt.yaml')

with open(yaml_path, 'r', encoding='utf-8') as file:
    prompt_config = yaml.safe_load(file)

# 2. Configure the Agent using the loaded YAML data
root_agent = Agent(
    model=model_name,
    name=prompt_config.get('name', 'graph_generator_agent'),
    description=prompt_config.get('description', 'An agent that generates various types of graphs based on user input.'),
    instruction=prompt_config.get('instruction', 'You are a graph generation agent. Use the provided tools to create graphs based on user requests.'),
    tools=[
        select_theme,
        generate_histogram,
        generate_pie_chart,
        generate_bar_chart,
        generate_multi_value_bar_chart,
        generate_line_chart,
        generate_multi_value_line_chart,
        generate_scatter_plot,
        generate_area_chart
    ],
)