import os
import json
import re
import base64
from io import BytesIO
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from mss import mss
from PIL import Image
from google import genai
from google.genai import types

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("\nWARNING: GEMINI_API_KEY was not found in your .env file!")
    client = None
else:
    print(f"\nGEMINI_API_KEY detected: {API_KEY[:6]}...{API_KEY[-4:]}")
    try:
        client = genai.Client(
            api_key=API_KEY,
            http_options=types.HttpOptions(
                timeout=60000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    except Exception as e:
        print(f"Failed to initialize Gemini client: {e}")
        client = None

DATA_FILE = "ementor_store.json"

def load_store():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_store():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(STUDENTS_STORE, f, indent=2)
    except Exception as e:
        print(f"Error saving store: {e}")

STUDENTS_STORE = load_store()

def get_or_create_student_session(student_id: str, email: str = None, name: str = None, department: str = None, year: int = None):
    if student_id not in STUDENTS_STORE:
        STUDENTS_STORE[student_id] = {
            "account": {
                "student_id": student_id,
                "email": email or f"{student_id}@aastu.edu.et",
                "name": name or "Student",
                "status": "active"
            },
            "profile": {
                "department": department or "Electromechanical Engineering",
                "year": year or 3,
                "background_skills": []
            },
            "knowledge_history": {
                "known_areas": [],
                "gaps": []
            },
            "courses": [],
            "projects": {},
            "active_project_id": None
        }
    else:
        session = STUDENTS_STORE[student_id]
        if email:
            session["account"]["email"] = email
        if name:
            session["account"]["name"] = name
        if department:
            session["profile"]["department"] = department
        if year is not None:
            session["profile"]["year"] = year
    save_store()
    return STUDENTS_STORE[student_id]

def extract_basic_profile_updates(session: dict, query: str):
    q_lower = query.lower()
    year_match = re.search(r'(?:year|grade)\D*?(\d)', q_lower)
    if year_match:
        session["profile"]["year"] = int(year_match.group(1))
            
    dept_match = re.search(r'(?:department|dept)\D*?(?:to\s+)?([a-zA-Z\s]+(?:engineering|science))', q_lower)
    if dept_match:
        session["profile"]["department"] = dept_match.group(1).strip().title()

    active_proj_id = session["active_project_id"]
    if active_proj_id and active_proj_id in session["projects"]:
        active_proj = session["projects"][active_proj_id]
        comp_match = re.search(r'(?:uses|has|is|now uses|now has)\s+(\d+(?:\.\d+)?)\s+([a-zA-Z\s]+)', q_lower)
        if comp_match:
            active_proj["current_state"][comp_match.group(2).strip()] = comp_match.group(1)
    save_store()

def retrieve_relevant_course_materials(session: dict, query: str) -> str:
    courses = session.get("courses", [])
    projects = session.get("projects", {})
    active_proj = projects.get(session.get("active_project_id"))
    
    query_tokens = set(re.findall(r'\w+', query.lower()))
    relevant_snippets = []
    
    for course in courses:
        for mat in course.get("materials", []):
            mat_text = f"{mat['title']} {mat['content']}"
            mat_tokens = set(re.findall(r'\w+', mat_text.lower()))
            overlap = len(query_tokens.intersection(mat_tokens))
            if overlap > 0 or len(query_tokens) == 0:
                relevant_snippets.append(f"[Course: {course['name']} -> {mat['title']}]: {mat['content']}")
                
    if active_proj and "files" in active_proj:
        for pfile in active_proj["files"]:
            relevant_snippets.append(f"[Active Project File ({pfile['title']})]: {pfile['content']}")
                
    if not relevant_snippets:
        return "No specific course materials or project files matched keywords."
        
    return "\n".join(relevant_snippets[:4])

def capture_screen_to_bytes() -> bytes:
    with mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()

def run_mentor_multimodal_inference(prompt: str, file_bytes: bytes = None, mime_type: str = "image/jpeg") -> dict:
    if not client:
        return {"status": "ERROR", "raw_error": "Gemini API key not detected in .env.", "fallback": True}
    try:
        contents = []
        if file_bytes:
            contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))
        contents.append(prompt)
        
        response = client.models.generate_content(model="gemini-2.5-flash", contents=contents)
        return {"status": "SUCCESS", "text": response.text}
    except Exception as e:
        print(f"Gemini API Error Details: {e}")
        return {"status": "ERROR", "raw_error": str(e), "fallback": True}

def extract_content_from_file(file_bytes: bytes, mime_type: str, title: str) -> str:
    if not client:
        return f"[Uploaded file: {title}]"
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                "Extract all important technical notes, formulas, specifications, schematics, and concepts from this file:"
            ]
        )
        return response.text
    except Exception as e:
        return f"[Error parsing file: {str(e)}]"

def run_agent_task(session: dict, task_type: str, prompt: str) -> str:
    if not client:
        return "Agent service unavailable: Gemini API key not detected."
    
    profile = session["profile"]
    active_proj = session["projects"].get(session["active_project_id"]) if session["active_project_id"] else None
    proj_context = f"Active Project: {active_proj['name']} (Objective: {active_proj['objective']})" if active_proj else "No active project."
    
    system_instructions = f"""You are EMentor Engineering Agent, an autonomous technical assistant.
Student Background: Department: {profile['department']}, Year {profile['year']}.
{proj_context}

Task Type Selected: {task_type.upper()}
User Request: '{prompt}'

AGENT GOVERNANCE & EXECUTION RULES:
1. Provide a rigorous, production-ready engineering solution.
2. If task is code, write clean Python or C++ code with comments optimized for robotics/microcontrollers.
3. If task is milestones, break the objective down into clear weekly engineering phases.
4. If task is calculator, show clear formulas and step-by-step arithmetic.
5. NEVER include introductory greetings or background statements. Be direct and precise.
6. Do not use LaTeX formatting. Use clean plain text and standard markdown."""

    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=system_instructions)
        return response.text
    except Exception as e:
        return f"Agent Execution Error: {str(e)}"

def run_ementor_pipeline(student_id: str, user_query: str, file_bytes: bytes = None, mime_type: str = "image/jpeg") -> dict:
    session = STUDENTS_STORE.get(student_id)
    if not session:
        return {"response": "Session not found. Please complete onboarding.", "active_project": None}
    
    extract_basic_profile_updates(session, user_query)
    
    profile = session["profile"]
    knowledge = session["knowledge_history"]
    active_proj_id = session["active_project_id"]
    active_project = session["projects"].get(active_proj_id) if active_proj_id else None
    
    q_lower = user_query.lower()
    if "what project am i working on" in q_lower or "my project" in q_lower:
        if active_project:
            return {
                "response": f"You are currently working on the active project {active_project['name']}.\n\nObjective: {active_project['objective']}\nDescription: {active_project['description']}",
                "active_project": active_project['name']
            }
        else:
            return {
                "response": "You do not currently have an active project selected in your workspace.",
                "active_project": None
            }

    state_str = "None recorded yet."
    if active_project and active_project["current_state"]:
        state_str = ", ".join([f"{k}: {v}" for k, v in active_project["current_state"].items()])
        
    retrieved_materials = retrieve_relevant_course_materials(session, user_query)
    known_str = ", ".join(knowledge["known_areas"]) if knowledge["known_areas"] else "None recorded."
    gaps_str = ", ".join(knowledge["gaps"]) if knowledge["gaps"] else "None recorded."

    system_prompt = f"""You are EMentor, an expert pedagogical tutor for engineering students.
Student Profile: Department: {profile['department']}, Year {profile['year']}.
Mastered Concepts: {known_str}
Knowledge Gaps: {gaps_str}

Retrieved Context (Course Materials & Project Files):
{retrieved_materials}

Active Project: {active_project['name'] if active_project else 'None'}
Project Objective: {active_project['objective'] if active_project else 'N/A'}
Project Description: {active_project['description'] if active_project else 'N/A'}
Current Project State / Verified Facts: {state_str}
Student Query / Attached Document Request: '{user_query}'

STRICT INSTRUCTIONS:
1. Answer the student's query directly and concisely. 
2. NEVER start your response with greetings (e.g., Hello, Hi), and DO NOT restate the student's background.
3. Actively leverage Knowledge Gaps for patient, detailed explanations and Mastered Concepts to skip redundancy.
4. DO NOT use LaTeX formatting. Write all numbers, units, and equations in clean plain text and standard markdown.
5. KNOWLEDGE EXTRACTION: Analyze the student's query. If they indicate they have mastered/understood a concept or are struggling/confused by a concept, you MUST append a JSON metadata block at the very end of your response in this exact format:
[KNOWLEDGE_UPDATE: {{"known": ["concept mastered"], "gaps": ["concept struggled with"]}}]
(Only include fields that apply; omit lists if empty)."""

    llm_result = run_mentor_multimodal_inference(system_prompt, file_bytes, mime_type)
    if llm_result.get("status") == "ERROR":
        raw_err = llm_result.get("raw_error", "Unknown error")
        response_text = f"API Error Details: {raw_err}"
    else:
        response_text = llm_result["text"]

    match = re.search(r'\[KNOWLEDGE_UPDATE:\s*(\{.*?\})\]', response_text)
    if match:
        try:
            update_json = json.loads(match.group(1))
            for k in update_json.get("known", []):
                if k and k not in knowledge["known_areas"]:
                    knowledge["known_areas"].append(k)
            for g in update_json.get("gaps", []):
                if g and g not in knowledge["gaps"]:
                    knowledge["gaps"].append(g)
            response_text = response_text.replace(match.group(0), "").strip()
        except Exception:
            pass

    if active_project:
        active_project["history"].append({"query": user_query, "response": response_text})

    save_store()
    return {
        "query": user_query,
        "response": response_text,
        "active_project": active_project['name'] if active_project else None,
        "session_data": {
            "profile": profile,
            "knowledge_history": knowledge,
            "courses": session["courses"],
            "projects": session["projects"],
            "active_project_id": active_proj_id
        }
    }

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EMentor AI — Student Workspace</title>
<style>
  :root { color-scheme: dark; --canvas: #081321; --surface: #101f31; --surface-raised: #15283c; --border: #263b50; --muted: #9aacc0; --text: #e7eff8; --accent: #55c8f5; --accent-strong: #159ed0; --danger: #fb8282; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(ellipse at 72% -12%, #17334a 0, transparent 42%), var(--canvas); color: var(--text); margin: 0; display: flex; height: 100vh; height: 100dvh; min-width: 0; overflow: hidden; }
  
  .onboard-overlay { position: fixed; inset: 0; padding: 20px; background: rgba(4, 12, 22, .82); backdrop-filter: blur(12px); display: flex; justify-content: center; align-items: flex-start; overflow-y: auto; z-index: 1000; }
  .wizard-card { margin: auto; background: linear-gradient(145deg, #172b40, #101d2d); border: 1px solid #34516a; border-radius: 20px; padding: 36px; width: 100%; max-width: 480px; display: flex; flex-direction: column; gap: 17px; box-shadow: 0 28px 90px rgba(0,0,0,.48); }
  .wizard-card h2 { margin: 0; color: var(--text); font-size: 25px; letter-spacing: -.03em; }
  .wizard-card > p { margin: -9px 0 2px; color: var(--muted); line-height: 1.55; }
  .eyebrow { color: var(--accent); font-size: 11px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }
  
  .sidebar { width: 258px; flex: 0 0 258px; background: rgba(13, 27, 42, .94); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
  .sidebar-header { padding: 25px 22px 21px; border-bottom: 1px solid var(--border); }
  .brand-lockup { display: flex; align-items: center; gap: 12px; }
  .brand-mark { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 12px; color: #062033; background: linear-gradient(145deg, #7be0ff, #28ace1); font-size: 19px; font-weight: 900; box-shadow: 0 6px 20px rgba(49, 180, 231, .2); }
  .sidebar-header h2 { margin: 0; font-size: 18px; color: var(--text); letter-spacing: -.02em; }
  .sidebar-header span { display: block; margin-top: 4px; font-size: 12px; color: var(--muted); line-height: 1.4; }
  .nav-caption { padding: 22px 13px 9px; color: #70869b; font-size: 10px; font-weight: 800; letter-spacing: .15em; text-transform: uppercase; }
  .nav-links { flex: 1; padding: 0 12px 16px; display: flex; flex-direction: column; gap: 5px; overflow-y: auto; }
  .nav-item { width: 100%; padding: 11px 13px; border: 1px solid transparent; border-radius: 10px; background: transparent; color: var(--muted); text-align: left; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; transition: background .18s ease, color .18s ease, border-color .18s ease, transform .18s ease; display: flex; align-items: center; gap: 11px; }
  .nav-item:hover { background: #14283b; color: var(--text); transform: translateX(2px); }
  .nav-item.active { background: linear-gradient(100deg, rgba(36, 161, 208, .19), rgba(36, 161, 208, .06)); color: #83ddff; border-color: rgba(85, 200, 245, .2); box-shadow: inset 3px 0 #55c8f5; }
  
  .main-content { min-width: 0; flex: 1; display: flex; flex-direction: column; height: 100vh; height: 100dvh; overflow: hidden; }
  .top-bar { min-height: 76px; padding: 14px 34px; background: rgba(12, 25, 39, .76); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; gap: 18px; }
  .top-bar h3 { margin: 0; font-size: 18px; letter-spacing: -.025em; color: var(--text); }
  .top-project-label { color: var(--muted); font-size: 12px; font-weight: 600; }
  .active-project-badge { display: inline-flex; align-items: center; gap: 7px; max-width: min(35vw, 300px); margin-left: 7px; padding: 7px 11px; border: 1px solid rgba(85, 200, 245, .24); border-radius: 999px; background: rgba(31, 117, 157, .2); color: #a2e7ff; font-size: 12px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: middle; }
  .active-project-badge::before { width: 6px; height: 6px; flex: 0 0 6px; border-radius: 50%; background: var(--accent); content: ""; }
  
  .view-panel { width: 100%; max-width: 1120px; min-height: 0; flex: 1; margin: 0 auto; padding: 30px 34px 42px; overflow-y: auto; display: none; flex-direction: column; gap: 20px; }
  .view-panel.active { display: flex; }
  
  .card { background: linear-gradient(145deg, rgba(21, 40, 60, .96), rgba(15, 30, 46, .96)); border: 1px solid var(--border); border-radius: 15px; padding: 23px; display: flex; flex-direction: column; gap: 14px; box-shadow: 0 8px 30px rgba(0, 0, 0, .1); }
  .card h3, .card h4 { margin-top: 0; margin-bottom: 2px; color: var(--text); letter-spacing: -.015em; }
  .card p { color: var(--muted); line-height: 1.6; }
  .form-group { display: flex; flex-direction: column; gap: 7px; }
  .form-group label { font-size: 12px; color: #b3c3d4; font-weight: 700; }
  .form-group input, .form-group select, .form-group textarea { width: 100%; min-height: 42px; padding: 10px 12px; border-radius: 9px; border: 1px solid #354c63; background: #0c1928; color: var(--text); font: inherit; font-size: 14px; outline: none; transition: border-color .18s, box-shadow .18s, background .18s; }
  .form-group textarea { resize: vertical; line-height: 1.5; }
  input::placeholder, textarea::placeholder { color: #71869a; }
  input:focus, select:focus, textarea:focus, .chat-input-area input:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(85, 200, 245, .13); }
  .btn { min-height: 42px; padding: 10px 16px; border-radius: 9px; border: 1px solid transparent; background: linear-gradient(135deg, #70d8ff, #42b8e9); color: #062033; font-weight: 800; font-size: 13px; cursor: pointer; transition: transform .18s ease, box-shadow .18s ease, background .18s ease, opacity .18s ease; }
  .btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 7px 18px rgba(52, 181, 231, .2); background: #8be2ff; }
  .btn:disabled { cursor: wait; opacity: .65; }
  .btn-secondary { background: #21364b; border-color: #354c63; color: #d7e5f2; }
  .btn-secondary:hover:not(:disabled) { background: #2b455e; }
  
  .chat-history { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; border: 1px solid var(--border); border-radius: 14px; background: rgba(14, 28, 43, .8); min-height: 300px; }
  .msg { max-width: min(85%, 760px); padding: 13px 16px; border-radius: 13px; line-height: 1.6; font-size: 14px; white-space: pre-line; overflow-wrap: anywhere; }
  .msg.user { background: linear-gradient(135deg, #158fbe, #1675a6); color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
  .msg.bot { background: #172a3d; border: 1px solid #2b4258; align-self: flex-start; color: #e2eaf3; border-bottom-left-radius: 4px; }
  .msg.pending { color: #9bdff7; border-color: rgba(85, 200, 245, .3); }
  .chat-input-area { display: flex; gap: 9px; padding: 9px; border: 1px solid var(--border); border-radius: 13px; background: #101f30; align-items: center; }
  .chat-input-area input[type="text"] { min-width: 0; min-height: 42px; flex: 1; padding: 10px 12px; border-radius: 8px; border: 1px solid transparent; background: #0b1725; color: white; font-size: 14px; outline: none; }
  .file-attach-btn { min-width: 42px; min-height: 42px; background: #1b3044; color: var(--accent); border: 1px solid #354d64; padding: 8px 12px; border-radius: 9px; cursor: pointer; font-size: 16px; transition: background .18s, transform .18s; }
  .file-attach-btn:hover { background: #29445c; transform: translateY(-1px); }
  
  .screen-inspect-btn { min-height: 40px; background: rgba(21, 130, 177, .18); color: #9be4ff; border: 1px solid rgba(85, 200, 245, .3); padding: 9px 14px; border-radius: 9px; font-weight: 700; cursor: pointer; font-size: 13px; transition: background .18s, border-color .18s; display: flex; align-items: center; gap: 7px; }
  .screen-inspect-btn:hover { background: rgba(21, 130, 177, .3); border-color: rgba(85, 200, 245, .55); }

  .agent-console { background: #0b1725; border: 1px solid #2b4258; border-radius: 11px; padding: 17px; font-family: "Cascadia Code", Consolas, monospace; font-size: 13px; color: #83dfff; min-height: 180px; max-height: 350px; overflow-y: auto; white-space: pre-line; line-height: 1.65; }
  .toast-region { position: fixed; right: 22px; bottom: 22px; z-index: 1200; display: grid; gap: 9px; width: min(380px, calc(100vw - 32px)); pointer-events: none; }
  .toast { padding: 13px 16px; border: 1px solid #34516a; border-radius: 11px; background: #152a3f; color: var(--text); box-shadow: 0 12px 36px rgba(0, 0, 0, .35); font-size: 13px; line-height: 1.5; animation: toast-in .2s ease-out; }
  .toast.success { border-color: rgba(85, 200, 245, .45); }
  .toast.error { border-color: rgba(251, 130, 130, .55); color: #ffd2d2; }
  @keyframes toast-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  @media (max-width: 820px) {
    body { height: auto; min-height: 100vh; min-height: 100dvh; overflow: auto; flex-direction: column; }
    .sidebar { width: 100%; flex: 0 0 auto; border-right: 0; border-bottom: 1px solid var(--border); }
    .sidebar-header { padding: 13px 18px; }
    .brand-mark { width: 34px; height: 34px; }
    .nav-caption { display: none; }
    .nav-links { flex: 0 0 auto; flex-direction: row; gap: 6px; padding: 8px 12px 11px; overflow-x: auto; }
    .nav-item { width: auto; flex: 0 0 auto; padding: 9px 11px; white-space: nowrap; }
    .nav-item.active { box-shadow: inset 0 -2px #55c8f5; }
    .main-content { height: auto; min-height: 65vh; min-height: 65dvh; overflow: visible; }
    .top-bar { position: sticky; top: 0; z-index: 5; min-height: 62px; padding: 12px 20px; backdrop-filter: blur(14px); }
    .view-panel { min-height: 55vh; padding: 22px 20px 34px; overflow: visible; }
  }
</style>
</head>
<body>

<div class="onboard-overlay" id="onboard-overlay">
  <form class="wizard-card" onsubmit="submitOnboarding(event)">
    <span class="eyebrow">Your engineering workspace</span>
    <h2>Let's get you started</h2>
    <p>Set up your student profile to personalize your mentor, courses, and project workspace.</p>
    <div class="form-group">
      <label>Full Name</label>
      <input type="text" id="onboard-name" placeholder="Enter your full name" autocomplete="name" required>
    </div>
    <div class="form-group">
      <label>University Email</label>
      <input type="text" id="onboard-email" placeholder="student_id@aastu.edu.et" required>
    </div>
    <div class="form-group">
      <label>Department</label>
      <select id="onboard-dept">
        <option value="Electromechanical Engineering" selected>Electromechanical Engineering</option>
        <option value="Mechanical Engineering">Mechanical Engineering</option>
        <option value="Electrical Engineering">Electrical Engineering</option>
        <option value="Software Engineering">Software Engineering</option>
      </select>
    </div>
    <div class="form-group">
      <label>Academic Year</label>
      <select id="onboard-year">
        <option value="1">Year 1</option>
        <option value="2">Year 2</option>
        <option value="3" selected>Year 3</option>
        <option value="4">Year 4</option>
        <option value="5">Year 5</option>
      </select>
    </div>
    <button class="btn" type="submit">Continue to workspace →</button>
  </form>
</div>

<div class="sidebar">
  <div class="sidebar-header">
    <div class="brand-lockup">
      <div class="brand-mark" aria-hidden="true">E</div>
      <div><h2>EMentor AI</h2><span id="sidebar-user">Student Workspace</span></div>
    </div>
  </div>
  <nav class="nav-links" aria-label="Main navigation">
    <div class="nav-caption">Workspace</div>
    <button type="button" class="nav-item active" data-view="home" aria-current="page" onclick="switchView('home', this)">🏠 Home</button>
    <button type="button" class="nav-item" data-view="mentor" onclick="switchView('mentor', this)">💬 Mentor</button>
    <button type="button" class="nav-item" data-view="courses" onclick="switchView('courses', this)">📚 Courses & Materials</button>
    <button type="button" class="nav-item" data-view="projects" onclick="switchView('projects', this)">📁 Projects</button>
    <button type="button" class="nav-item" data-view="knowledge" onclick="switchView('knowledge', this)">🧠 Knowledge</button>
    <button type="button" class="nav-item" data-view="agent" onclick="switchView('agent', this)">🤖 Agent</button>
    <button type="button" class="nav-item" data-view="settings" onclick="switchView('settings', this)">⚙ Settings</button>
  </nav>
</div>

<div class="main-content">
  <div class="top-bar">
    <h3 id="view-title">Home Dashboard</h3>
    <div class="top-project-label">Active project <span class="active-project-badge" id="top-active-proj">None</span></div>
  </div>

  <div class="view-panel active" id="view-home">
    <div class="card">
      <h2 style="margin:0; color:#38bdf8;" id="home-greeting">Welcome back!</h2>
      <p id="home-profile-info" style="color:#94a3b8; margin:0;"></p>
    </div>
    <div class="card">
      <h3>Active Project Status</h3>
      <p id="home-project-status">No active project yet. Create a project to start working with EMentor.</p>
      <button class="btn" style="width: fit-content;" onclick="switchView('projects')">Manage Projects</button>
    </div>
    <div class="card">
      <h3>Quick Access</h3>
      <div class="quick-access-actions" style="display:flex; gap:10px; flex-wrap:wrap;">
        <button class="btn" onclick="switchView('mentor')">Open Mentor Chat</button>
        <button class="btn btn-secondary" onclick="switchView('courses')">View Courses</button>
      </div>
    </div>
  </div>

  <div class="view-panel" id="view-mentor">
    <div class="chat-history" id="chat">
      <div class="msg bot">Ask a question or click the Inspect Active Screen button below to analyze your active desktop app.</div>
    </div>
    <div id="chat-file-indicator" style="font-size: 12px; color: #38bdf8; display: none;">📎 File attached ready to send</div>
    
    <div>
      <button class="screen-inspect-btn" onclick="inspectScreen()">🖥️ Inspect active screen</button>
    </div>

    <div class="chat-input-area">
      <input type="file" id="chat-file-input" accept=".pdf,image/*" style="display:none;" onchange="handleChatFileSelect()">
      <button class="file-attach-btn" type="button" onclick="document.getElementById('chat-file-input').click()" title="Attach PDF or picture">📎</button>
      <input type="text" id="query" aria-label="Message EMentor" placeholder="Ask EMentor a question..." onkeypress="if(event.key === 'Enter') sendQuery()">
      <button class="btn" id="chat-send-button" onclick="sendQuery()">Send</button>
    </div>
  </div>

  <div class="view-panel" id="view-courses">
    <div class="card">
      <h3>+ Upload PDF or Picture Material</h3>
      <div class="form-group"><label>Course Name</label><input type="text" id="course-name" placeholder="e.g., Mechatronic Systems"></div>
      <div class="form-group"><label>Material Title</label><input type="text" id="material-title" placeholder="e.g., Lecture 3 PDF / Circuit Diagram"></div>
      <div class="form-group">
        <label>Select PDF or Image File (.pdf, .png, .jpg)</label>
        <input type="file" id="course-file" accept=".pdf,image/*" style="padding: 8px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: white;">
      </div>
      <button class="btn" style="width: fit-content;" onclick="uploadCourseFile()">+ Upload & Index File</button>
    </div>
    <div class="card">
      <h3>Enrolled Courses & Indexed Materials</h3>
      <div id="courses-list" style="display:flex; flex-direction:column; gap:10px;"></div>
    </div>
  </div>

  <div class="view-panel" id="view-projects">
    <div class="card">
      <h3>Create New Project</h3>
      <div class="form-group"><label>Project Name</label><input type="text" id="new-proj-name" placeholder="e.g., Autonomous Line-Following Robot"></div>
      <div class="form-group"><label>Objective</label><input type="text" id="new-proj-obj" placeholder="e.g., Build a robot that follows tracks autonomously."></div>
      <div class="form-group"><label>Description</label><textarea id="new-proj-desc" rows="2" placeholder="Brief system description..."></textarea></div>
      <div class="form-group">
        <label>Attach Project File / Schematic (Optional)</label>
        <input type="file" id="new-proj-file" accept=".pdf,image/*" style="padding: 8px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: white;">
      </div>
      <button class="btn" style="width: fit-content;" onclick="createProject()">+ Create Project</button>
    </div>
    <div class="card">
      <h3>Your Projects</h3>
      <div id="projects-list" style="display:flex; flex-direction:column; gap:10px;"></div>
    </div>
  </div>

  <div class="view-panel" id="view-knowledge">
    <div class="card">
      <h3>Student Knowledge & Ability History</h3>
      <p style="color:#94a3b8; font-size:13px; margin:0;">Concepts update automatically when you chat with EMentor, or you can add them manually below.</p>
      
      <div style="display:flex; gap:20px; margin-top:10px;">
        <div style="flex:1; display:flex; flex-direction:column; gap:8px;">
          <h4 style="margin:0; color:#38bdf8;">Mastered Concepts</h4>
          <div style="display:flex; gap:6px;">
            <input type="text" id="new-known-input" placeholder="e.g., PID Tuning" style="flex:1; padding:8px; border-radius:6px; border:1px solid #475569; background:#0f172a; color:white; font-size:13px;">
            <button class="btn" style="padding:8px 12px; font-size:13px;" onclick="addKnowledgeItem('known')">+ Add</button>
          </div>
          <ul id="known-areas-list" style="margin-top:0; padding-left:18px; color:#e2e8f0;"><li>No known areas recorded yet.</li></ul>
        </div>
        
        <div style="flex:1; display:flex; flex-direction:column; gap:8px;">
          <h4 style="margin:0; color:#f87171;">Knowledge Gaps</h4>
          <div style="display:flex; gap:6px;">
            <input type="text" id="new-gap-input" placeholder="e.g., Laplace Transforms" style="flex:1; padding:8px; border-radius:6px; border:1px solid #475569; background:#0f172a; color:white; font-size:13px;">
            <button class="btn" style="padding:8px 12px; font-size:13px; background:#f87171; color:#0f172a;" onclick="addKnowledgeItem('gap')">+ Add</button>
          </div>
          <ul id="gaps-list" style="margin-top:0; padding-left:18px; color:#e2e8f0;"><li>No knowledge gaps recorded yet.</li></ul>
        </div>
      </div>
    </div>
  </div>

  <div class="view-panel" id="view-agent">
    <div class="card">
      <h3>Autonomous Engineering Agent</h3>
      <p style="color:#94a3b8; font-size:13px; margin:0;">Execute specialized engineering workflows.</p>
      <div class="form-group" style="margin-top:10px;">
        <label>Select Agent Task Mode</label>
        <select id="agent-task-type">
          <option value="code">Robotics Code Generator & Debugger</option>
          <option value="milestones">Project Milestone Decomposition</option>
          <option value="calculator">Electromechanical Parameter Solver</option>
        </select>
      </div>
      <div class="form-group">
        <label>Task Prompt / Specification</label>
        <textarea id="agent-prompt" rows="3" placeholder="Enter task prompt..."></textarea>
      </div>
      <button class="btn" id="agent-run-button" style="width: fit-content;" onclick="executeAgentTask()">Execute agent task</button>
    </div>
    <div class="card">
      <h3>Agent Execution Console</h3>
      <div class="agent-console" id="agent-output">Ready for task execution...</div>
    </div>
  </div>

  <div class="view-panel" id="view-settings">
    <div class="card">
      <h3>Account & Settings</h3>
      <div class="form-group"><label>Student ID</label><input type="text" id="set-id" readonly></div>
      <div class="form-group"><label>Email</label><input type="text" id="set-email" readonly></div>
      <div class="form-group"><label>Department</label><input type="text" id="set-dept"></div>
      <div class="form-group"><label>Year</label><input type="text" id="set-year"></div>
    </div>
  </div>
</div>

<div class="toast-region" id="toast-region" aria-live="polite"></div>

<script>
let studentSession = null;
let currentProjects = {};
let activeProjId = null;
let selectedChatFile = null;
let toastTimeout = null;

function showToast(message, type = 'info') {
    const region = document.getElementById('toast-region');
    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    region.replaceChildren(toast);
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => toast.remove(), 4200);
}

function switchView(viewName, element) {
    document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(i => {
        i.classList.remove('active');
        i.removeAttribute('aria-current');
    });
    document.getElementById('view-' + viewName).classList.add('active');
    const activeItem = element || document.querySelector('[data-view="' + viewName + '"]');
    if(activeItem) {
        activeItem.classList.add('active');
        activeItem.setAttribute('aria-current', 'page');
    }
    const titles = {
        'home': 'Home Dashboard',
        'mentor': 'Mentor Assistant Workspace',
        'courses': 'Courses & Material Source',
        'projects': 'Project Management',
        'knowledge': 'Knowledge & Ability History',
        'agent': 'Autonomous Engineering Agent',
        'settings': 'Account Settings'
    };
    document.getElementById('view-title').innerText = titles[viewName];
}

function handleChatFileSelect() {
    const input = document.getElementById('chat-file-input');
    if (input.files.length > 0) {
        selectedChatFile = input.files[0];
        document.getElementById('chat-file-indicator').style.display = 'block';
        document.getElementById('chat-file-indicator').innerText = 'Attached: ' + selectedChatFile.name;
    }
}

async function submitOnboarding(event) {
    event.preventDefault();
    const name = document.getElementById('onboard-name').value.trim();
    const email = document.getElementById('onboard-email').value.trim();
    const department = document.getElementById('onboard-dept').value;
    const year = parseInt(document.getElementById('onboard-year').value);
    
    if(!name || !email) {
        showToast('Please enter your name and email.', 'error');
        return;
    }
    
    document.getElementById('onboard-overlay').style.display = 'none';
    const studentId = email.split('@')[0] || 'student_' + Date.now();

    try {
        const res = await fetch('/api/session', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ student_id: studentId, name, email, department, year })
        });
        if (res.ok) {
            const data = await res.json();
            updateSessionUI(data);
        } else {
            throw new Error('Server status ' + res.status);
        }
    } catch (err) {
        updateSessionUI({
            account: { student_id: studentId, email: email, name: name, status: 'active' },
            profile: { department: department, year: year, background_skills: [] },
            knowledge_history: { known_areas: ['PID Tuning'], gaps: ['Laplace Transforms'] },
            courses: [],
            projects: {},
            active_project_id: null
        });
    }
}

function updateSessionUI(data) {
    studentSession = data;
    document.getElementById('sidebar-user').innerText = data.account.name + ' (' + data.profile.department + ')';
    document.getElementById('home-greeting').innerText = 'Welcome back, ' + data.account.name + '!';
    document.getElementById('home-profile-info').innerText = data.profile.department + ' • Year ' + data.profile.year;
    document.getElementById('set-id').value = data.account.student_id;
    document.getElementById('set-email').value = data.account.email;
    document.getElementById('set-dept').value = data.profile.department;
    document.getElementById('set-year').value = data.profile.year;
    renderCourses(data.courses);
    renderKnowledge(data.knowledge_history);
    updateUIProjects(data.projects, data.active_project_id);
    document.getElementById('onboard-overlay').style.display = 'none';
    showToast('Your workspace is ready, ' + data.account.name + '.', 'success');
}

async function addKnowledgeItem(type) {
    const inputId = type === 'known' ? 'new-known-input' : 'new-gap-input';
    const itemText = document.getElementById(inputId).value.trim();
    if(!itemText) {
        showToast('Enter a concept before adding it.', 'error');
        return;
    }
    const res = await fetch('/api/knowledge/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ student_id: studentSession.account.student_id, type: type, item: itemText })
    });
    const data = await res.json();
    studentSession.knowledge_history = data.knowledge_history;
    renderKnowledge(studentSession.knowledge_history);
    document.getElementById(inputId).value = '';
    showToast('Concept updated successfully.', 'success');
}

async function executeAgentTask() {
    const taskType = document.getElementById('agent-task-type').value;
    const prompt = document.getElementById('agent-prompt').value.trim();
    const consoleEl = document.getElementById('agent-output');
    if(!prompt) {
        showToast('Add a task prompt before starting the agent.', 'error');
        return;
    }
    const runButton = document.getElementById('agent-run-button');
    runButton.disabled = true;
    runButton.textContent = 'Working...';
    consoleEl.innerText = 'Initializing Agent Environment...\\nExecuting task with Gemini 2.5 Flash...';
    try {
        const res = await fetch('/api/agent/execute', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ student_id: studentSession.account.student_id, task_type: taskType, prompt: prompt })
        });
        if (!res.ok) throw new Error('Server status ' + res.status);
        const data = await res.json();
        consoleEl.innerText = data.result;
    } catch(err) {
        consoleEl.innerText = 'The agent request failed. Please check your connection.';
        showToast('Could not run the agent task.', 'error');
    } finally {
        runButton.disabled = false;
        runButton.textContent = 'Execute agent task';
    }
}

async function inspectScreen() {
    const chat = document.getElementById('chat');
    const customPrompt = prompt("What would you like EMentor to check on your screen?", "Analyze this screen and tell me how to fix any errors or improve this design:");
    if (!customPrompt) return;
    
    chat.innerHTML += '<div class="msg user">[Screen Inspection Requested]: ' + customPrompt + '</div>';
    chat.scrollTop = chat.scrollHeight;
    
    for (let i = 3; i > 0; i--) {
        chat.innerHTML += `<div class="msg bot temp-countdown">Switch to your target app in ${i}...</div>`;
        chat.scrollTop = chat.scrollHeight;
        await new Promise(resolve => setTimeout(resolve, 1000));
        const tempMsg = chat.querySelector('.temp-countdown');
        if (tempMsg) tempMsg.remove();
    }
    
    chat.innerHTML += '<div class="msg bot" id="screen-loading">Capturing screen and analyzing with Gemini...</div>';
    chat.scrollTop = chat.scrollHeight;
    
    try {
        const res = await fetch('/api/screen/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ student_id: studentSession.account.student_id, query: customPrompt })
        });
        const data = await res.json();
        document.getElementById('screen-loading').remove();
        chat.innerHTML += '<div class="msg bot">' + data.response + '</div>';
        chat.scrollTop = chat.scrollHeight;
        if(data.session_data) {
            studentSession.profile = data.session_data.profile;
            studentSession.knowledge_history = data.session_data.knowledge_history;
            studentSession.projects = data.session_data.projects;
            renderKnowledge(studentSession.knowledge_history);
            updateUIProjects(studentSession.projects, data.session_data.active_project_id);
        }
    } catch(err) {
        document.getElementById('screen-loading').remove();
        chat.innerHTML += '<div class="msg bot">Error capturing screen or connecting to server.</div>';
    }
}

async function uploadCourseFile() {
    const courseName = document.getElementById('course-name').value.trim();
    const title = document.getElementById('material-title').value.trim();
    const fileInput = document.getElementById('course-file');
    if(!courseName || !title || fileInput.files.length === 0) {
        showToast('Enter course name, title, and choose a file.', 'error');
        return;
    }
    const file = fileInput.files[0];
    const reader = new FileReader();
    reader.onload = async function(e) {
        const base64Data = e.target.result.split(',')[1];
        showToast('Uploading and indexing your material...', 'info');
        try {
            const res = await fetch('/api/course/upload', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ student_id: studentSession.account.student_id, course_name: courseName, title: title, mime_type: file.type, file_data: base64Data })
            });
            if (!res.ok) throw new Error('Server status ' + res.status);
            const data = await res.json();
            renderCourses(data.courses);
            document.getElementById('course-name').value = '';
            document.getElementById('material-title').value = '';
            fileInput.value = '';
            showToast('Material uploaded and indexed.', 'success');
        } catch(err) {
            showToast('Could not upload material.', 'error');
        }
    };
    reader.readAsDataURL(file);
}

async function createProject() {
    const name = document.getElementById('new-proj-name').value.trim();
    const objective = document.getElementById('new-proj-obj').value.trim();
    const description = document.getElementById('new-proj-desc').value.trim();
    const fileInput = document.getElementById('new-proj-file');
    if(!name) {
        showToast('Enter a project name.', 'error');
        return;
    }
    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        const reader = new FileReader();
        reader.onload = async function(e) {
            const base64Data = e.target.result.split(',')[1];
            await sendCreateProjectRequest(name, objective, description, file.type, file.name, base64Data);
        };
        reader.readAsDataURL(file);
    } else {
        await sendCreateProjectRequest(name, objective, description, null, null, null);
    }
}

async function sendCreateProjectRequest(name, objective, description, mimeType, fileName, fileData) {
    const res = await fetch('/api/project/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ student_id: studentSession.account.student_id, name, objective, description, mime_type: mimeType, file_name: fileName, file_data: fileData })
    });
    const data = await res.json();
    updateUIProjects(data.projects, data.active_project_id);
    document.getElementById('new-proj-name').value = '';
    document.getElementById('new-proj-obj').value = '';
    document.getElementById('new-proj-desc').value = '';
    document.getElementById('new-proj-file').value = '';
    switchView('projects');
    showToast('Project created successfully.', 'success');
}

async function uploadFileToExistingProject(projId) {
    const fileInput = document.getElementById('proj-file-' + projId);
    if (!fileInput || fileInput.files.length === 0) {
        showToast('Choose a file to attach.', 'error');
        return;
    }
    const file = fileInput.files[0];
    const reader = new FileReader();
    reader.onload = async function(e) {
        const base64Data = e.target.result.split(',')[1];
        const res = await fetch('/api/project/add_file', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ student_id: studentSession.account.student_id, project_id: projId, mime_type: file.type, file_name: file.name, file_data: base64Data })
        });
        const data = await res.json();
        updateUIProjects(data.projects, data.active_project_id);
        showToast('File attached.', 'success');
    };
    reader.readAsDataURL(file);
}

async function setActiveProject(projId) {
    const res = await fetch('/api/project/switch', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ student_id: studentSession.account.student_id, project_id: projId })
    });
    const data = await res.json();
    updateUIProjects(data.projects, data.active_project_id);
}

function updateUIProjects(projects, activeId) {
    currentProjects = projects || {};
    activeProjId = activeId;
    const activeName = (activeId && currentProjects[activeId]) ? currentProjects[activeId].name : 'None';
    document.getElementById('top-active-proj').innerText = activeName;
    if(activeId && currentProjects[activeId]) {
        let fileCount = currentProjects[activeId].files ? currentProjects[activeId].files.length : 0;
        document.getElementById('home-project-status').innerHTML = 'Current Active Project: ' + currentProjects[activeId].name + '<br>Objective: ' + currentProjects[activeId].objective + '<br>Attached Files: ' + fileCount;
    } else {
        document.getElementById('home-project-status').innerText = 'No active project yet. Create a project to start working with EMentor.';
    }
    let html = '';
    const keys = Object.keys(currentProjects);
    if(keys.length === 0) {
        html = '<p style="color:#94a3b8;">No projects created yet.</p>';
    } else {
        keys.forEach(k => {
            const p = currentProjects[k];
            const isActive = k === activeId;
            let fileList = '';
            if (p.files && p.files.length > 0) {
                p.files.forEach(f => {
                    fileList += '<br><span style="font-size:11px; color:#38bdf8;">📎 ' + f.title + '</span>';
                });
            }
            html += '<div style="background:#0f172a; padding:14px; border-radius:8px; border:1px solid ' + (isActive ? '#38bdf8' : '#334155') + '; display:flex; flex-direction:column; gap:10px;">' +
                '<div style="display:flex; justify-content:space-between; align-items:center;">' +
                    '<div>' +
                       '<h4 style="margin:0; color:white;">' + p.name + ' ' + (isActive ? '(Active)' : '') + '</h4>' +
                       '<p style="margin:4px 0 0 0; font-size:13px; color:#94a3b8;">' + (p.objective || 'No objective provided') + fileList + '</p>' +
                    '</div>' +
                    (!isActive ? '<button class="btn" onclick="setActiveProject(\\'' + k + '\\')">Set Active</button>' : '') +
                '</div>' +
                '<div style="display:flex; gap:8px; align-items:center; margin-top:4px; border-top:1px solid #334155; padding-top:8px;">' +
                    '<input type="file" id="proj-file-' + k + '" accept=".pdf,image/*" style="font-size:12px; color:#94a3b8;">' +
                    '<button class="btn btn-secondary" style="padding:6px 10px; font-size:12px;" onclick="uploadFileToExistingProject(\\'' + k + '\\')">+ Add File</button>' +
                '</div>' +
            '</div>';
        });
    }
    document.getElementById('projects-list').innerHTML = html;
}

function renderCourses(courses) {
    let html = '';
    if (!courses || courses.length === 0) {
        html = '<p style="color:#94a3b8;">No course materials indexed yet.</p>';
    } else {
        courses.forEach(c => {
            let mats = c.materials.map(m => '<li>' + m.title + ': ' + m.content.substring(0, 90) + '...</li>').join('');
            html += '<div style="background:#0f172a; padding:14px; border-radius:8px; border:1px solid #334155;">' +
                '<h4 style="margin:0 0 8px 0; color:#38bdf8;">' + c.name + '</h4>' +
                '<ul style="margin:0; padding-left:18px; color:#94a3b8; font-size:13px;">' + mats + '</ul>' +
            '</div>';
        });
    }
    document.getElementById('courses-list').innerHTML = html;
}

function renderKnowledge(kh) {
    if(!kh) return;
    const knownEl = document.getElementById('known-areas-list');
    const gapsEl = document.getElementById('gaps-list');
    knownEl.innerHTML = (kh.known_areas && kh.known_areas.length > 0) ? kh.known_areas.map(a => '<li>' + a + '</li>').join('') : '<li>No known areas recorded yet.</li>';
    gapsEl.innerHTML = (kh.gaps && kh.gaps.length > 0) ? kh.gaps.map(g => '<li>' + g + '</li>').join('') : '<li>No knowledge gaps recorded yet.</li>';
}

function readChatFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            if (typeof reader.result === 'string') {
                resolve(reader.result);
            } else {
                reject(new Error('The selected file could not be read.'));
            }
        };
        reader.onerror = () => reject(reader.error || new Error('The selected file could not be read.'));
        reader.onabort = () => reject(new Error('Reading the selected file was cancelled.'));
        reader.readAsDataURL(file);
    });
}

async function sendQuery() {
    const q = document.getElementById('query').value.trim();
    if(!q && !selectedChatFile) {
        showToast('Type a question or attach a file first.', 'error');
        return;
    }
    const chat = document.getElementById('chat');
    const sendButton = document.getElementById('chat-send-button');
    if (sendButton.disabled) return;
    sendButton.disabled = true;
    sendButton.textContent = 'Sending...';
    try {
        const payload = {
            student_id: studentSession.account.student_id,
            query: q || 'Please analyze this attached file.'
        };
        const file = selectedChatFile;
        if (file) {
            try {
                const dataUrl = await readChatFileAsDataUrl(file);
                payload.mime_type = file.type;
                payload.file_data = dataUrl.split(',')[1];
            } catch (err) {
                console.error('Could not read the attached chat file:', err);
                showToast('Could not read the attached file. Your message is still available to retry.', 'error');
                return;
            }
        }

        let displayText = q;
        if (file) {
            displayText += ' [Attached File: ' + file.name + ']';
        }
        chat.innerHTML += '<div class="msg user">' + displayText + '</div>';
        document.getElementById('query').value = '';
        chat.scrollTop = chat.scrollHeight;

        if (file) {
            selectedChatFile = null;
            document.getElementById('chat-file-indicator').style.display = 'none';
            document.getElementById('chat-file-input').value = '';
        }
        await executeChatRequest(payload);
    } finally {
        sendButton.disabled = false;
        sendButton.textContent = 'Send';
    }
}

async function executeChatRequest(payload) {
    const chat = document.getElementById('chat');
    const pendingMessage = document.createElement('div');
    pendingMessage.className = 'msg bot pending';
    pendingMessage.textContent = 'EMentor is thinking...';
    chat.appendChild(pendingMessage);
    chat.scrollTop = chat.scrollHeight;
    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
            signal: AbortSignal.timeout(65000)
        });
        if (!res.ok) throw new Error('Server status ' + res.status);
        const data = await res.json();
        pendingMessage.remove();
        chat.innerHTML += '<div class="msg bot">' + data.response + '</div>';
        chat.scrollTop = chat.scrollHeight;
        if(data.session_data) {
            studentSession.profile = data.session_data.profile;
            studentSession.knowledge_history = data.session_data.knowledge_history;
            studentSession.projects = data.session_data.projects;
            renderKnowledge(studentSession.knowledge_history);
            updateUIProjects(studentSession.projects, data.session_data.active_project_id);
            document.getElementById('home-profile-info').innerText = studentSession.profile.department + ' • Year ' + studentSession.profile.year;
            document.getElementById('set-dept').value = studentSession.profile.department;
            document.getElementById('set-year').value = studentSession.profile.year;
        }
    } catch(err) {
        pendingMessage.remove();
        console.error('Chat request failed:', err);
        const errorMessage = document.createElement('div');
        errorMessage.className = 'msg bot';
        errorMessage.textContent = 'Could not complete your request: ' + err.message;
        chat.appendChild(errorMessage);
        chat.scrollTop = chat.scrollHeight;
    }
}
</script>
</body>
</html>
"""

class EMentorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(HTML_UI.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode('utf-8'))
        except Exception:
            data = {}

        if parsed.path == "/api/session":
            sid = data.get("student_id", "default")
            session = get_or_create_student_session(
                sid, data.get("email"), data.get("name"), data.get("department"), int(data.get("year", 3))
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "account": session["account"],
                "profile": session["profile"],
                "courses": session["courses"],
                "knowledge_history": session["knowledge_history"],
                "projects": session["projects"],
                "active_project_id": session["active_project_id"]
            }).encode("utf-8"))

        elif parsed.path == "/api/knowledge/add":
            sid = data.get("student_id")
            k_type = data.get("type")
            item = data.get("item")
            session = STUDENTS_STORE.get(sid)
            if session and item:
                if k_type == 'known' and item not in session["knowledge_history"]["known_areas"]:
                    session["knowledge_history"]["known_areas"].append(item)
                elif k_type == 'gap' and item not in session["knowledge_history"]["gaps"]:
                    session["knowledge_history"]["gaps"].append(item)
                save_store()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "knowledge_history": session["knowledge_history"] if session else {}
            }).encode("utf-8"))

        elif parsed.path == "/api/screen/analyze":
            sid = data.get("student_id")
            query = data.get("query", "Analyze my screen and provide feedback.")
            screen_bytes = capture_screen_to_bytes()
            result = run_ementor_pipeline(sid, query, file_bytes=screen_bytes, mime_type="image/jpeg")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))

        elif parsed.path == "/api/agent/execute":
            sid = data.get("student_id")
            task_type = data.get("task_type")
            prompt = data.get("prompt")
            session = STUDENTS_STORE.get(sid)
            result = run_agent_task(session, task_type, prompt) if session else "Session not found."
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"result": result}).encode("utf-8"))

        elif parsed.path == "/api/course/upload":
            sid = data.get("student_id")
            session = STUDENTS_STORE.get(sid)
            if session:
                c_name = data.get("course_name")
                title = data.get("title")
                mime_type = data.get("mime_type")
                file_bytes = base64.b64decode(data.get("file_data"))
                extracted_notes = extract_content_from_file(file_bytes, mime_type, title)
                course_obj = next((c for c in session["courses"] if c["name"].lower() == c_name.lower()), None)
                if not course_obj:
                    course_obj = {"course_id": f"c_{len(session['courses'])+1}", "name": c_name, "materials": []}
                    session["courses"].append(course_obj)
                course_obj["materials"].append({"title": title, "content": extracted_notes})
                save_store()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"courses": session["courses"] if session else []}).encode("utf-8"))

        elif parsed.path == "/api/project/create":
            sid = data.get("student_id")
            session = STUDENTS_STORE.get(sid)
            if session:
                proj_id = f"proj_{len(session['projects']) + 1}"
                proj_files = []
                if data.get("file_data") and data.get("mime_type"):
                    file_bytes = base64.b64decode(data.get("file_data"))
                    extracted_text = extract_content_from_file(file_bytes, data.get("mime_type"), data.get("file_name", "Project File"))
                    proj_files.append({"title": data.get("file_name", "Project File"), "content": extracted_text})

                session["projects"][proj_id] = {
                    "name": data.get("name"),
                    "objective": data.get("objective"),
                    "description": data.get("description"),
                    "files": proj_files,
                    "current_state": {},
                    "history": []
                }
                if not session["active_project_id"]:
                    session["active_project_id"] = proj_id
                save_store()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "projects": session["projects"] if session else {},
                "active_project_id": session["active_project_id"] if session else None
            }).encode("utf-8"))

        elif parsed.path == "/api/project/add_file":
            sid = data.get("student_id")
            proj_id = data.get("project_id")
            session = STUDENTS_STORE.get(sid)
            if session and proj_id in session["projects"]:
                file_bytes = base64.b64decode(data.get("file_data"))
                extracted_text = extract_content_from_file(file_bytes, data.get("mime_type"), data.get("file_name", "Project File"))
                session["projects"][proj_id]["files"].append({
                    "title": data.get("file_name", "Project File"),
                    "content": extracted_text
                })
                save_store()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "projects": session["projects"] if session else {},
                "active_project_id": session["active_project_id"] if session else None
            }).encode("utf-8"))

        elif parsed.path == "/api/project/switch":
            sid = data.get("student_id")
            proj_id = data.get("project_id")
            session = STUDENTS_STORE.get(sid)
            if session and proj_id in session["projects"]:
                session["active_project_id"] = proj_id
                save_store()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "projects": session["projects"] if session else {},
                "active_project_id": session["active_project_id"] if session else None
            }).encode("utf-8"))

        elif parsed.path == "/api/chat":
            sid = data.get("student_id")
            query = data.get("query", "")
            file_bytes = base64.b64decode(data.get("file_data")) if data.get("file_data") else None
            mime_type = data.get("mime_type") if data.get("mime_type") else None
            result = run_ementor_pipeline(sid, query, file_bytes, mime_type)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 8000))
    server_address = ('0.0.0.0', port)
    httpd = ThreadingHTTPServer(server_address, EMentorHandler)
    print(f"\nEMentor Server active on port {port}\n")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()