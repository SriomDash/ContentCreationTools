import os
from typing import List, Dict, Union
import plotly.express as px
import pandas as pd

# --- THEME MANAGEMENT ---
THEME_MAP = {
    "cyberpunk": "plotly_dark",      
    "minimalist": "simple_white",    
    "corporate": "plotly_white",     
    "academic": "ggplot2",           
    "vibrant": "plotly"              
}

def select_theme(context_or_vibe: str) -> Dict[str, str]:
    """
    Identifies the best visual theme for the graph based on user request or data context.
    Must return one of 5 options: 'cyberpunk', 'minimalist', 'corporate', 'academic', or 'vibrant'.
    """
    vibe = context_or_vibe.lower().strip()
    if vibe not in THEME_MAP:
        vibe = "vibrant" 
        
    return {
        "status": "success", 
        "theme_name": vibe, 
        "plotly_template": THEME_MAP[vibe]
    }

def _save_and_return(fig, title: str) -> Dict[str, str]:
    """Helper function to save charts as PNGs in the 'graphs' directory."""
    try:
        os.makedirs("graphs", exist_ok=True)
        
        safe_title = "".join(x for x in title if x.isalnum() or x in " -_").replace(" ", "_").lower()
        filepath = os.path.join("graphs", f"{safe_title}.png")
        
        fig.write_image(filepath)
        
        return {"status": "success", "action": "saved_as_image", "file_path": filepath}
        
    except ValueError as e:
        if "kaleido" in str(e).lower():
            return {"status": "error", "message": "Missing image rendering dependency. Run: pip install -U kaleido"}
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- GRAPH GENERATION TOOLS ---
def generate_histogram(title: str, values: List[Union[int, float]], x_label: str = "Values", template: str = "plotly") -> Dict[str, str]:
    """Generates a vertical histogram showing the frequency distribution of a single set of numerical data."""
    try:
        df = pd.DataFrame({x_label: values})
        fig = px.histogram(df, x=x_label, title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def generate_pie_chart(title: str, labels: List[str], values: List[Union[int, float]], template: str = "plotly") -> Dict[str, str]:
    """Generates a pie chart from the provided data."""
    try:
        df = pd.DataFrame({"Categories": labels, "Values": values})
        fig = px.pie(df, names="Categories", values="Values", title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def generate_bar_chart(title: str, labels: List[str], values: List[Union[int, float]], template: str = "plotly") -> Dict[str, str]:
    """Generates a standard vertical bar chart."""
    try:
        df = pd.DataFrame({"Categories": labels, "Values": values})
        fig = px.bar(df, x="Categories", y="Values", title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def generate_horizontal_bar_chart(title: str, labels: List[str], values: List[Union[int, float]], template: str = "plotly") -> Dict[str, str]:
    """Generates a horizontal bar chart from the provided data."""
    try:
        df = pd.DataFrame({"Categories": labels, "Values": values})
        fig = px.bar(df, x="Values", y="Categories", orientation='h', title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def generate_multi_value_bar_chart(title: str, x_labels: List[str], group_labels: List[str], values: List[Union[int, float]], template: str = "plotly") -> Dict[str, str]:
    """Generates a grouped multi-value bar chart. 
    CRITICAL: x_labels, group_labels, and values must all be the same length."""
    try:
        df = pd.DataFrame({"Axis_Labels": x_labels, "Groups": group_labels, "Values": values})
        fig = px.bar(df, x="Axis_Labels", y="Values", color="Groups", barmode='group', title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def generate_line_chart(title: str, x_values: List[Union[str, int, float]], y_values: List[Union[int, float]], template: str = "plotly") -> Dict[str, str]:
    """Generates a simple line chart from the provided data."""
    try:
        df = pd.DataFrame({"X_Axis": x_values, "Y_Axis": y_values})
        fig = px.line(df, x="X_Axis", y="Y_Axis", title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def generate_multi_value_line_chart(title: str, x_values: List[Union[str, int, float]], group_labels: List[str], y_values: List[Union[int, float]], template: str = "plotly") -> Dict[str, str]:
    """Generates a multi-line chart comparing different groups over the same X axis."""
    try:
        df = pd.DataFrame({"X_Axis": x_values, "Groups": group_labels, "Y_Axis": y_values})
        fig = px.line(df, x="X_Axis", y="Y_Axis", color="Groups", title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def generate_scatter_plot(title: str, x_values: List[Union[int, float]], y_values: List[Union[int, float]], template: str = "plotly") -> Dict[str, str]:
    """Generates a scatter plot from the provided numerical data."""
    try:
        df = pd.DataFrame({"X_Axis": x_values, "Y_Axis": y_values})
        fig = px.scatter(df, x="X_Axis", y="Y_Axis", title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def generate_area_chart(title: str, x_values: List[Union[str, int, float]], y_values: List[Union[int, float]], template: str = "plotly") -> Dict[str, str]:
    """Generates an area chart from the provided data."""
    try:
        df = pd.DataFrame({"X_Axis": x_values, "Y_Axis": y_values})
        fig = px.area(df, x="X_Axis", y="Y_Axis", title=title, template=template)
        return _save_and_return(fig, title)
    except Exception as e:
        return {"status": "error", "message": str(e)}