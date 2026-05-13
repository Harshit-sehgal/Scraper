import sys

def remove_functions(filepath, funcs_to_remove):
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    out_lines = []
    skip = False
    indent_level = 0
    
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith('def ') or stripped.startswith('async def '):
            name_part = stripped.split('def ')[1]
            func_name = name_part.split('(')[0].strip()
            
            if func_name in funcs_to_remove:
                skip = True
                indent_level = len(line) - len(stripped)
                continue
                
        if skip:
            if stripped == '' or stripped.startswith('#'):
                continue # still skipping
            current_indent = len(line) - len(stripped)
            if current_indent <= indent_level:
                skip = False
            else:
                continue # still inside the function
                
        if not skip:
            out_lines.append(line)
            
    # Add imports at the top
    imports = """
from app.llm_bridge import _extract_json_payload, _should_retry_http_error, _call_openai_compatible_json, _call_openai_compatible_text, _groq_model_candidates, llm_json as _llm_json, llm_json_fast as _llm_json_fast, llm_text as _llm_text
from app.html_utils import _compact_text, _normalized_text_key, _is_placeholder_value, _is_entity_name_field, _is_noise_name_value, _is_likely_noise_entity, _is_empty_value, _is_likely_noise_row, fetch_page_content, clean_html_for_selectors, _valid_email, _valid_phone
from app.selector_engine import _detect_table_headers, _analyze_page_data_type, _intelligent_column_mapping, _get_field_keywords, _infer_field_type_from_examples, build_selector_prompt, extract_css_selectors
from app.scraper_protocols import ScraperProtocol, ExtractionContract
"""
    
    # insert after existing imports
    for i, line in enumerate(out_lines):
        # find the first non-import, non-docstring, non-empty line
        if not line.startswith('import ') and not line.startswith('from ') and line.strip() != '' and not line.startswith('\"\"\"'):
            out_lines.insert(i, imports)
            break
            
    with open(filepath, 'w') as f:
        f.writelines(out_lines)

funcs = {
    '_extract_json_payload', '_should_retry_http_error', '_call_openai_compatible_json', 
    '_call_openai_compatible_text', '_groq_model_candidates', '_llm_json', '_llm_json_fast', 
    '_llm_text', '_compact_text', '_normalized_text_key', '_is_placeholder_value', 
    '_is_entity_name_field', '_is_noise_name_value', '_is_likely_noise_entity', '_is_empty_value', 
    '_is_likely_noise_row', 'fetch_page_content', 'clean_html_for_selectors', '_valid_email', 
    '_valid_phone', '_detect_table_headers', '_analyze_page_data_type', '_intelligent_column_mapping', 
    '_get_field_keywords', '_infer_field_type_from_examples', 'build_selector_prompt', 
    'extract_css_selectors'
}

remove_functions('backend/app/scraper.py', funcs)
