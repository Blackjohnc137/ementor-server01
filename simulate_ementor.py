import os
import sqlite3
from flask import Flask, render_template_string, request, redirect, session, url_for, flash
from dotenv import load_dotenv
from google import genai

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

DB_FILE = "ementor.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("DROP TABLE IF EXISTS messages")
    cursor.execute("DROP TABLE IF EXISTS chat_sessions")
    cursor.execute("DROP TABLE IF EXISTS courses_materials")
    cursor.execute("DROP TABLE IF EXISTS knowledge_history")
    cursor.execute("DROP TABLE IF EXISTS projects")
    cursor.execute("DROP TABLE IF EXISTS students")
    
    cursor.execute('''
        CREATE TABLE students (
            student_id TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            year INTEGER NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            title TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            sender TEXT,
            text TEXT,
            FOREIGN KEY (session_id) REFERENCES chat_sessions (id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE courses_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            course_name TEXT NOT NULL,
            material_title TEXT NOT NULL,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE knowledge_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            category TEXT NOT NULL,
            concept TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            name TEXT NOT NULL,
            objective TEXT NOT NULL,
            description TEXT NOT NULL,
            filename TEXT,
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')

    conn.commit()
    conn.close()

init_db()

UI_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EMentor Platform</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="h-full flex flex-col font-sans">
    {% if not session.get('student_id') %}
    <div class="flex flex-col items-center justify-center flex-grow px-4 py-8">
        <div class="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
            <div class="text-center mb-6">
                <h1 class="text-2xl font-bold tracking-tight text-sky-400">EMentor Portal</h1>
                <p class="text-xs text-slate-400 mt-1">Sign in or register your student profile</p>
            </div>
            {% with messages = get_flashed_messages() %}
              {% if messages %}
                <div class="mb-4 p-3 bg-red-950/50 border border-red-800 text-red-300 text-xs rounded-xl text-center">
                  {{ messages[0] }}
                </div>
              {% endif %}
            {% endwith %}
            <form method="POST" action="/login" class="space-y-4">
                <div>
                    <label class="block text-xs font-medium text-slate-400 mb-1">Full Name</label>
                    <input type="text" name="name" required placeholder="Yohannes Tadesse" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:border-sky-400 transition text-sm">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-400 mb-1">Student ID</label>
                    <input type="text" name="student_id" required placeholder="ETS 1234/15" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:border-sky-400 transition font-mono text-sm">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-400 mb-1">Password</label>
                    <input type="password" name="password" required placeholder="••••••••" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:border-sky-400 transition text-sm">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-400 mb-1">Department</label>
                    <input type="text" name="department" required placeholder="Electromechanical Engineering" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:border-sky-400 transition text-sm">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-400 mb-1">Year of Study</label>
                    <select name="year" required class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:border-sky-400 transition text-sm">
                        <option value="1">Year 1</option>
                        <option value="2">Year 2</option>
                        <option value="3" selected>Year 3</option>
                        <option value="4">Year 4</option>
                        <option value="5">Year 5</option>
                    </select>
                </div>
                <button type="submit" class="w-full bg-sky-400 hover:bg-sky-500 text-slate-950 font-semibold py-3 rounded-xl transition shadow-lg mt-2 text-sm">Sign In / Register</button>
            </form>
        </div>
    </div>
    {% else %}
    <div class="flex h-screen overflow-hidden">
        <aside class="w-72 bg-slate-900 border-r border-slate-800 flex flex-col justify-between p-4 hidden md:flex">
            <div>
                <div class="px-3 py-4 mb-4 border-b border-slate-800 flex items-center space-x-3">
                    <div class="w-10 h-10 bg-sky-400 text-slate-950 rounded-xl flex items-center justify-center font-bold text-lg shadow">E</div>
                    <div>
                        <h1 class="font-bold text-slate-100 text-sm">EMentor AI</h1>
                        <div class="text-xs text-sky-400 truncate max-w-[170px]">{{ session.get('name') }}</div>
                        <div class="text-[10px] text-slate-400">{{ session.get('department') }}</div>
                    </div>
                </div>

                <div class="px-3 pb-2 text-[10px] font-semibold tracking-wider text-slate-500">NAVIGATION</div>

                <nav class="space-y-1">
                    <a href="/" class="flex items-center space-x-3 px-3 py-2.5 rounded-xl {{ 'bg-slate-800 text-sky-400 border border-slate-700' if active_tab == 'home' else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition text-sm font-medium">
                        <span>Home</span>
                    </a>
                    <a href="/mentor" class="flex items-center space-x-3 px-3 py-2.5 rounded-xl {{ 'bg-slate-800 text-sky-400 border border-slate-700' if active_tab == 'mentor' else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition text-sm font-medium">
                        <span>Mentor & Chats</span>
                    </a>
                    <a href="/courses" class="flex items-center space-x-3 px-3 py-2.5 rounded-xl {{ 'bg-slate-800 text-sky-400 border border-slate-700' if active_tab == 'courses' else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition text-sm font-medium">
                        <span>Courses & Materials</span>
                    </a>
                    <a href="/projects" class="flex items-center space-x-3 px-3 py-2.5 rounded-xl {{ 'bg-slate-800 text-sky-400 border border-slate-700' if active_tab in ['projects', 'project_detail'] else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition text-sm font-medium">
                        <span>Projects</span>
                    </a>
                    <a href="/knowledge" class="flex items-center space-x-3 px-3 py-2.5 rounded-xl {{ 'bg-slate-800 text-sky-400 border border-slate-700' if active_tab == 'knowledge' else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition text-sm font-medium">
                        <span>Knowledge Base</span>
                    </a>
                    <a href="/agent" class="flex items-center space-x-3 px-3 py-2.5 rounded-xl {{ 'bg-slate-800 text-sky-400 border border-slate-700' if active_tab == 'agent' else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition text-sm font-medium">
                        <span>Agent Console</span>
                    </a>
                    <a href="/settings" class="flex items-center space-x-3 px-3 py-2.5 rounded-xl {{ 'bg-slate-800 text-sky-400 border border-slate-700' if active_tab == 'settings' else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition text-sm font-medium">
                        <span>Settings</span>
                    </a>
                </nav>
            </div>
            
            <div class="border-t border-slate-800 pt-3 px-2">
                <div class="text-[11px] text-sky-400 mb-2 font-mono">{{ session.get('student_id') }}</div>
                <a href="/logout" class="block text-center text-xs bg-slate-800 hover:bg-slate-700 py-2 rounded-lg transition text-slate-300">Logout</a>
            </div>
        </aside>

        <div class="flex-1 flex flex-col bg-slate-950 overflow-hidden">
            <header class="border-b border-slate-800 bg-slate-900 px-6 py-4 flex justify-between items-center">
                <h1 class="text-base font-semibold text-slate-100">{{ page_title }}</h1>
                <div class="flex items-center space-x-2 text-xs text-slate-400">
                    <span>Active project:</span>
                    <span class="bg-slate-800 text-slate-200 px-2.5 py-1 rounded-md font-medium">None</span>
                </div>
            </header>

            {% if active_tab == 'home' %}
            <main class="flex-1 max-w-4xl w-full mx-auto p-6 overflow-y-auto space-y-6">
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-xl space-y-3">
                    <h2 class="text-2xl font-bold text-sky-400">Welcome, {{ session.get('name') }}.</h2>
                    <p class="text-sm text-slate-300 leading-relaxed">Your AI workspace is online and connected to the database. Access your course materials, manage active projects, and consult your AI mentor.</p>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow">
                        <div class="text-xs font-medium text-slate-400 mb-1">Student ID</div>
                        <div class="text-sm font-semibold text-sky-400 font-mono">{{ session.get('student_id') }}</div>
                    </div>
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow">
                        <div class="text-xs font-medium text-slate-400 mb-1">Department</div>
                        <div class="text-sm font-semibold text-emerald-400">{{ session.get('department') }}</div>
                    </div>
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow">
                        <div class="text-xs font-medium text-slate-400 mb-1">Year of Study</div>
                        <div class="text-sm font-semibold text-cyan-400">Year {{ session.get('year') }}</div>
                    </div>
                </div>
            </main>

            {% elif active_tab == 'mentor' %}
            <main class="flex-1 max-w-5xl w-full mx-auto p-4 flex gap-4 overflow-hidden">
                <div class="w-64 bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col justify-between hidden lg:flex">
                    <div class="space-y-3 overflow-y-auto flex-grow">
                        <div class="flex justify-between items-center">
                            <span class="text-xs font-semibold text-slate-400">Chat Threads</span>
                            <a href="/mentor/new" class="text-xs bg-sky-400 hover:bg-sky-500 text-slate-950 font-semibold px-2 py-1 rounded-lg transition">+ New Chat</a>
                        </div>
                        <div class="space-y-1.5 pt-2">
                            {% for sid, stitle in chat_sessions %}
                                <a href="/mentor?session={{ sid }}" class="block text-xs p-2 rounded-xl truncate transition {{ 'bg-sky-400/20 text-sky-300 border border-sky-500/30 font-semibold' if current_session_id == sid else 'text-slate-300 hover:bg-slate-800' }}">
                                    {{ stitle }}
                                </a>
                            {% endfor %}
                        </div>
                    </div>
                    <div class="pt-3 border-t border-slate-800">
                        <a href="/mentor/clear?session={{ current_session_id }}" class="block text-center text-xs text-red-400 hover:text-red-300 bg-red-950/40 border border-red-900/50 py-2 rounded-xl transition">Clear Thread</a>
                    </div>
                </div>

                <div class="flex-1 flex flex-col overflow-hidden bg-slate-900 border border-slate-800 rounded-2xl p-4">
                    <div class="flex justify-between items-center mb-3 pb-2 border-b border-slate-800">
                        <span class="text-xs text-sky-400 font-medium">Thread: {{ current_session_title }}</span>
                        <div class="lg:hidden flex space-x-2">
                            <a href="/mentor/new" class="text-xs bg-sky-400 text-slate-950 font-semibold px-2 py-1 rounded">+ New</a>
                            <a href="/mentor/clear?session={{ current_session_id }}" class="text-xs bg-red-950 text-red-300 px-2 py-1 rounded">Clear</a>
                        </div>
                    </div>

                    <div class="flex-grow overflow-y-auto space-y-4 pr-2 mb-4">
                        {% if not history %}
                            <div class="flex justify-start">
                                <div class="bg-slate-950 border border-slate-800 rounded-2xl px-5 py-4 max-w-lg text-slate-300 shadow text-sm">
                                    Hello {{ session.get('name') }}. I am your AI Mentor. Ask questions about your coursework, upload reference materials, or use screen inspection.
                                </div>
                            </div>
                        {% endif %}
                        {% for sender, text in history %}
                            <div class="flex {{ 'justify-end' if sender == 'You' else 'justify-start' }}">
                                <div class="{{ 'bg-sky-400 text-slate-950 font-medium' if sender == 'You' else 'bg-slate-950 border border-slate-800 text-slate-300' }} rounded-2xl px-5 py-4 max-w-lg shadow whitespace-pre-wrap text-sm">
                                    {{ text }}
                                </div>
                            </div>
                        {% endfor %}
                    </div>

                    <div class="space-y-3 pt-2 border-t border-slate-800">
                        <div class="flex items-center justify-between">
                            <button type="button" id="inspectScreenBtn" onclick="captureScreen()" class="bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-200 text-xs px-3.5 py-2 rounded-xl transition shadow">
                                <span id="inspectText">Inspect active screen</span>
                            </button>
                            <span id="screenStatus" class="text-[11px] text-emerald-400 hidden">Screen captured</span>
                        </div>

                        <form method="POST" action="/mentor/chat" enctype="multipart/form-data" class="flex gap-2 items-center">
                            <input type="hidden" name="session_id" value="{{ current_session_id }}">
                            <input type="hidden" name="screen_capture" id="screenCaptureInput">
                            
                            <label class="cursor-pointer bg-slate-950 hover:bg-slate-800 border border-slate-800 px-3.5 py-3 rounded-xl text-slate-400 hover:text-slate-200 transition text-sm" title="Attach file">
                                <span>Attach</span>
                                <input type="file" name="chat_file" class="hidden">
                            </label>
                            
                            <input type="text" name="message" required autocomplete="off" placeholder="Ask a technical question..." class="flex-grow bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition">
                            <button type="submit" class="bg-sky-400 hover:bg-sky-500 text-slate-950 font-semibold px-5 py-3 rounded-xl transition shadow-lg text-sm">Send</button>
                        </form>
                    </div>
                </div>
            </main>

            <script>
                async function captureScreen() {
                    const btnText = document.getElementById('inspectText');
                    const status = document.getElementById('screenStatus');
                    try {
                        const stream = await navigator.mediaDevices.getDisplayMedia({ video: { mediaSource: 'screen' } });
                        const track = stream.getVideoTracks()[0];
                        const imageCapture = new ImageCapture(track);
                        const bitmap = await imageCapture.grabFrame();
                        
                        const canvas = document.createElement('canvas');
                        canvas.width = bitmap.width;
                        canvas.height = bitmap.height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(bitmap, 0, 0);
                        
                        track.stop();
                        
                        const dataUrl = canvas.toDataURL('image/jpeg');
                        document.getElementById('screenCaptureInput').value = dataUrl;
                        
                        btnText.innerText = "Captured ✓";
                        status.classList.remove('hidden');
                    } catch (err) {
                        console.error(err);
                    }
                }
            </script>

            {% elif active_tab == 'courses' %}
            <main class="flex-1 max-w-4xl w-full mx-auto p-6 overflow-y-auto space-y-8">
                <div>
                    <h2 class="text-xl font-bold text-slate-100">Courses & Materials</h2>
                    <p class="text-xs text-slate-400 mt-1">Upload PDF documents or images to serve as RAG context for your mentor.</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
                    <h3 class="text-sm font-semibold text-sky-400 mb-4">Upload New Material</h3>
                    <form method="POST" action="/courses/add" enctype="multipart/form-data" class="space-y-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Course Name</label>
                            <input type="text" name="course_name" required placeholder="e.g., Mechatronic Systems" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Material Title</label>
                            <input type="text" name="material_title" required placeholder="e.g., Lecture 3 Notes" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Select File (.pdf, .png, .jpg)</label>
                            <input type="file" name="material_file" required class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-300 text-xs file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-sky-400">
                        </div>
                        <button type="submit" class="bg-sky-400 hover:bg-sky-500 text-slate-950 font-semibold px-6 py-2.5 rounded-xl transition text-sm">Upload & Index</button>
                    </form>
                </div>
                <div class="space-y-4">
                    <h3 class="text-sm font-semibold text-slate-200">Indexed Course Documents</h3>
                    {% if courses %}
                        {% for cid, cname, mtitle, fname, content in courses %}
                        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow space-y-2">
                            <div class="flex justify-between items-center">
                                <span class="text-xs font-semibold px-2.5 py-1 bg-slate-800 text-sky-400 rounded-lg">{{ cname }}</span>
                                <span class="text-xs font-mono text-slate-400">{{ fname }}</span>
                            </div>
                            <h4 class="text-base font-semibold text-slate-200">{{ mtitle }}</h4>
                            <p class="text-xs text-slate-400 bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono">{{ content }}</p>
                        </div>
                        {% endfor %}
                    {% else %}
                        <p class="text-sm text-slate-400 italic">No indexed materials uploaded yet.</p>
                    {% endif %}
                </div>
            </main>

            {% elif active_tab == 'projects' %}
            <main class="flex-1 max-w-4xl w-full mx-auto p-6 overflow-y-auto space-y-8">
                <div>
                    <h2 class="text-xl font-bold text-slate-100">Project Management</h2>
                    <p class="text-xs text-slate-400 mt-1">Manage engineering projects and attach relevant schematics or files.</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
                    <h3 class="text-sm font-semibold text-sky-400 mb-4">Create Project</h3>
                    <form method="POST" action="/projects/add" enctype="multipart/form-data" class="space-y-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Project Name</label>
                            <input type="text" name="name" required placeholder="Autonomous Robot" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Objective</label>
                            <input type="text" name="objective" required placeholder="Build a line-following system." class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Description</label>
                            <textarea name="description" rows="2" required placeholder="Brief description..." class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition"></textarea>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Attach File (Optional)</label>
                            <input type="file" name="project_file" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-300 text-xs file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-sky-400">
                        </div>
                        <button type="submit" class="bg-sky-400 hover:bg-sky-500 text-slate-950 font-semibold px-6 py-2.5 rounded-xl transition text-sm">Create Project</button>
                    </form>
                </div>
                <div class="space-y-4">
                    <h3 class="text-sm font-semibold text-slate-200">Active Projects</h3>
                    {% if projects %}
                        {% for pid, pname, pobj, pdesc, pfile in projects %}
                        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow flex justify-between items-center">
                            <div class="space-y-1">
                                <h4 class="text-base font-bold text-sky-300">{{ pname }}</h4>
                                <p class="text-xs text-slate-300">Objective: {{ pobj }}</p>
                                <p class="text-xs text-slate-400">{{ pdesc }}</p>
                                {% if pfile %}
                                    <div class="text-xs text-cyan-400">File: {{ pfile }}</div>
                                {% endif %}
                            </div>
                            <form method="POST" action="/projects/delete/{{ pid }}">
                                <button type="submit" class="text-xs bg-red-950/60 hover:bg-red-900 border border-red-800 text-red-300 px-3 py-2 rounded-xl transition">Delete</button>
                            </form>
                        </div>
                        {% endfor %}
                    {% else %}
                        <p class="text-sm text-slate-400 italic">No projects created yet.</p>
                    {% endif %}
                </div>
            </main>

            {% elif active_tab == 'knowledge' %}
            <main class="flex-1 max-w-4xl w-full mx-auto p-6 overflow-y-auto space-y-8">
                <div>
                    <h2 class="text-xl font-bold text-slate-100">Knowledge Base</h2>
                    <p class="text-xs text-slate-400 mt-1">Concepts update automatically through chat analysis or manual additions.</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="bg-slate-950 border border-slate-800 rounded-2xl p-5 space-y-4">
                            <h4 class="text-sm font-bold text-sky-400">Mastered Concepts</h4>
                            <form method="POST" action="/knowledge/add" class="flex gap-2">
                                <input type="hidden" name="category" value="mastered">
                                <input type="text" name="concept" required placeholder="e.g., PID Tuning" class="flex-grow bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition">
                                <button type="submit" class="bg-sky-400 hover:bg-sky-500 text-slate-950 font-semibold px-3 py-2 rounded-xl transition text-xs">Add</button>
                            </form>
                            <ul class="space-y-2 pt-2">
                                {% set m_found = False %}
                                {% for kid, cat, concept in knowledge %}
                                    {% if cat == 'mastered' %}
                                        {% set m_found = True %}
                                        <li class="text-xs text-slate-300 bg-slate-900 px-3 py-2 rounded-xl border border-slate-800 flex justify-between items-center">
                                            <span>{{ concept }}</span>
                                            <a href="/knowledge/delete/{{ kid }}" class="text-red-400 hover:text-red-300">×</a>
                                        </li>
                                    {% endif %}
                                {% endfor %}
                                {% if not m_found %}
                                    <li class="text-xs text-slate-400 italic">No mastered concepts recorded yet.</li>
                                {% endif %}
                            </ul>
                        </div>
                        <div class="bg-slate-950 border border-slate-800 rounded-2xl p-5 space-y-4">
                            <h4 class="text-sm font-bold text-rose-400">Knowledge Gaps</h4>
                            <form method="POST" action="/knowledge/add" class="flex gap-2">
                                <input type="hidden" name="category" value="gap">
                                <input type="text" name="concept" required placeholder="e.g., Laplace Transforms" class="flex-grow bg-slate-900 border border-slate-800 rounded-xl px-4 py-2 text-slate-100 text-sm focus:outline-none focus:border-rose-400 transition">
                                <button type="submit" class="bg-rose-400 hover:bg-rose-500 text-slate-950 font-semibold px-3 py-2 rounded-xl transition text-xs">Add</button>
                            </form>
                            <ul class="space-y-2 pt-2">
                                {% set g_found = False %}
                                {% for kid, cat, concept in knowledge %}
                                    {% if cat == 'gap' %}
                                        {% set g_found = True %}
                                        <li class="text-xs text-slate-300 bg-slate-900 px-3 py-2 rounded-xl border border-slate-800 flex justify-between items-center">
                                            <span>{{ concept }}</span>
                                            <a href="/knowledge/delete/{{ kid }}" class="text-red-400 hover:text-red-300">×</a>
                                        </li>
                                    {% endif %}
                                {% endfor %}
                                {% if not g_found %}
                                    <li class="text-xs text-slate-400 italic">No knowledge gaps recorded yet.</li>
                                {% endif %}
                            </ul>
                        </div>
                    </div>
                </div>
            </main>

            {% elif active_tab == 'agent' %}
            <main class="flex-1 max-w-4xl w-full mx-auto p-6 overflow-y-auto space-y-8">
                <div>
                    <h2 class="text-xl font-bold text-slate-100">Agent Console</h2>
                    <p class="text-xs text-slate-400 mt-1">Execute specialized engineering workflows, generate code, and solve calculations.</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
                    <form method="POST" action="/agent/run" class="space-y-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Task Mode</label>
                            <select name="task_mode" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition">
                                <option>Robotics Code Generator & Debugger</option>
                                <option>Kinematic Equations Solver</option>
                                <option>Circuit & PCB Analysis Agent</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Task Prompt</label>
                            <textarea name="prompt" rows="3" required placeholder="Enter task specification..." class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 text-sm focus:outline-none focus:border-sky-400 transition"></textarea>
                        </div>
                        <button type="submit" class="bg-sky-400 hover:bg-sky-500 text-slate-950 font-semibold px-6 py-2.5 rounded-xl transition text-sm">Execute Task</button>
                    </form>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
                    <h3 class="text-sm font-semibold text-slate-200">Execution Console</h3>
                    <div class="bg-slate-950 border border-slate-800 rounded-2xl p-5 font-mono text-xs text-sky-300 min-h-[160px] max-h-[350px] overflow-y-auto whitespace-pre-wrap">
                        {% if agent_output %}
                            {{ agent_output }}
                        {% else %}
                            Ready for task execution...
                        {% endif %}
                    </div>
                </div>
            </main>

            {% elif active_tab == 'settings' %}
            <main class="flex-1 max-w-4xl w-full mx-auto p-6 overflow-y-auto space-y-6">
                <div>
                    <h2 class="text-xl font-bold text-slate-100">Account Settings</h2>
                    <p class="text-xs text-slate-400 mt-1">Manage student profile information.</p>
                </div>
                <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5">
                    <div class="space-y-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Full Name</label>
                            <div class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 text-sm">{{ session.get('name') }}</div>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Student ID</label>
                            <div class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 text-sm font-mono">{{ session.get('student_id') }}</div>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Department</label>
                            <div class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 text-sm">{{ session.get('department') }}</div>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Year</label>
                            <div class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 text-sm">Year {{ session.get('year') }}</div>
                        </div>
                    </div>
                </div>
            </main>
            {% endif %}
        </div>
    </div>
    {% endif %}
</body>
</html>
"""

@app.route("/")
def home():
    if 'student_id' not in session:
        return render_template_string(UI_TEMPLATE)
    return render_template_string(UI_TEMPLATE, active_tab='home', page_title="Home")

@app.route("/mentor")
def mentor():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM chat_sessions WHERE student_id = ?", (session['student_id'],))
    sessions_list = cursor.fetchall()
    
    if not sessions_list:
        cursor.execute("INSERT INTO chat_sessions (student_id, title) VALUES (?, ?)", (session['student_id'], 'General Discussion'))
        conn.commit()
        cursor.execute("SELECT id, title FROM chat_sessions WHERE student_id = ?", (session['student_id'],))
        sessions_list = cursor.fetchall()
        
    current_sid = request.args.get('session', type=int)
    session_ids = [s[0] for s in sessions_list]
    if not current_sid or current_sid not in session_ids:
        current_sid = session_ids[0]
        
    current_title = next((s[1] for s in sessions_list if s[0] == current_sid), 'General Discussion')
    
    cursor.execute("SELECT sender, text FROM messages WHERE session_id = ?", (current_sid,))
    history = cursor.fetchall()
    conn.close()
    
    return render_template_string(UI_TEMPLATE, chat_sessions=sessions_list, current_session_id=current_sid, current_session_title=current_title, history=history, active_tab='mentor', page_title="AI Mentor")

@app.route("/mentor/new")
def new_mentor_chat():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM chat_sessions WHERE student_id = ?", (session['student_id'],))
    cnt = cursor.fetchone()[0]
    title = f"Chat Session {cnt + 1}"
    cursor.execute("INSERT INTO chat_sessions (student_id, title) VALUES (?, ?)", (session['student_id'], title))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return redirect(url_for('mentor', session=new_id))

@app.route("/courses")
def courses():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, course_name, material_title, filename, content FROM courses_materials WHERE student_id = ?", (session['student_id'],))
    c_list = cursor.fetchall()
    conn.close()
    return render_template_string(UI_TEMPLATE, courses=c_list, active_tab='courses', page_title="Courses & Materials")

@app.route("/projects")
def projects():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, objective, description, filename FROM projects WHERE student_id = ?", (session['student_id'],))
    p_list = cursor.fetchall()
    conn.close()
    return render_template_string(UI_TEMPLATE, projects=p_list, active_tab='projects', page_title="Projects")

@app.route("/knowledge")
def knowledge():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, category, concept FROM knowledge_history WHERE student_id = ?", (session['student_id'],))
    k_list = cursor.fetchall()
    conn.close()
    return render_template_string(UI_TEMPLATE, knowledge=k_list, active_tab='knowledge', page_title="Knowledge Base")

@app.route("/agent")
def agent():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    return render_template_string(UI_TEMPLATE, active_tab='agent', page_title="Agent Console")

@app.route("/settings")
def settings():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    return render_template_string(UI_TEMPLATE, active_tab='settings', page_title="Settings")

@app.route("/courses/add", methods=["POST"])
def add_course():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    cname = request.form.get("course_name")
    mtitle = request.form.get("material_title")
    file = request.files.get("material_file")
    fname = file.filename if file and file.filename != '' else "uploaded_document.pdf"
    content = f"Indexed content from uploaded file '{fname}' for course '{cname}'."
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO courses_materials (student_id, course_name, material_title, filename, content) VALUES (?, ?, ?, ?, ?)", 
                   (session['student_id'], cname, mtitle, fname, content))
    conn.commit()
    conn.close()
    return redirect(url_for('courses'))

@app.route("/projects/add", methods=["POST"])
def add_project():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    name = request.form.get("name")
    objective = request.form.get("objective")
    description = request.form.get("description")
    file = request.files.get("project_file")
    fname = file.filename if file and file.filename != '' else None

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO projects (student_id, name, objective, description, filename) VALUES (?, ?, ?, ?, ?)", 
                   (session['student_id'], name, objective, description, fname))
    conn.commit()
    conn.close()
    return redirect(url_for('projects'))

@app.route("/projects/delete/<int:pid>", methods=["POST"])
def delete_project(pid):
    if 'student_id' not in session:
        return redirect(url_for('home'))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ? AND student_id = ?", (pid, session['student_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('projects'))

@app.route("/knowledge/add", methods=["POST"])
def add_knowledge():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    category = request.form.get("category")
    concept = request.form.get("concept")
    if category and concept:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO knowledge_history (student_id, category, concept) VALUES (?, ?, ?)", 
                       (session['student_id'], category, concept))
        conn.commit()
        conn.close()
    return redirect(url_for('knowledge'))

@app.route("/knowledge/delete/<int:kid>")
def delete_knowledge(kid):
    if 'student_id' not in session:
        return redirect(url_for('home'))
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM knowledge_history WHERE id = ? AND student_id = ?", (kid, session['student_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('knowledge'))

@app.route("/agent/run", methods=["POST"])
def run_agent():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    task_mode = request.form.get("task_mode")
    prompt = request.form.get("prompt")
    
    output_text = f"Task: {task_mode}\nPrompt: {prompt}\n\n"
    if client:
        try:
            res = client.models.generate_content(
                model="gemini-2.5-flash", 
                contents=f"Act as an expert engineering agent for Electromechanical Systems. Task: {task_mode}. Prompt: {prompt}. Generate professional Python code, circuit equations, or calculation steps."
            )
            output_text += res.text
        except Exception as e:
            output_text += f"Error executing task: {str(e)}"
    else:
        output_text += "Error: GEMINI_API_KEY environment variable is not configured."

    return render_template_string(UI_TEMPLATE, agent_output=output_text, active_tab='agent', page_title="Agent Console")

@app.route("/mentor/clear")
def clear_mentor():
    if 'student_id' in session:
        sid = request.args.get('session', type=int)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if sid:
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
        conn.commit()
        conn.close()
    return redirect(url_for('mentor', session=sid))

@app.route("/login", methods=["POST"])
def login():
    name = request.form.get("name").strip()
    student_id = request.form.get("student_id").strip()
    password = request.form.get("password")
    department = request.form.get("department", "Electromechanical Engineering").strip()
    year = request.form.get("year", 3, type=int)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, password, name, department, year FROM students WHERE student_id = ?", (student_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute("""
            INSERT INTO students (student_id, password, name, department, year)
            VALUES (?, ?, ?, ?, ?)
        """, (student_id, password, name, department, year))
        conn.commit()
        cursor.execute("SELECT student_id, password, name, department, year FROM students WHERE student_id = ?", (student_id,))
        user = cursor.fetchone()
    else:
        cursor.execute("UPDATE students SET name = ?, department = ?, year = ? WHERE student_id = ?", (name, department, year, student_id))
        conn.commit()
        
    conn.close()
    
    if user and user[1] == password:
        session['student_id'] = user[0]
        session['name'] = name
        session['department'] = department
        session['year'] = year
        return redirect(url_for('home'))
    
    flash("Invalid password.")
    return redirect(url_for('home'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route("/mentor/chat", methods=["POST"])
def mentor_chat():
    if 'student_id' not in session:
        return redirect(url_for('home'))
    
    user_message = request.form.get("message")
    session_id = request.form.get("session_id", type=int)
    screen_capture = request.form.get("screen_capture")
    student_id = session['student_id']

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (session_id, 'You', user_message))
    conn.commit()

    cursor.execute("SELECT course_name, material_title, content FROM courses_materials WHERE student_id = ?", (student_id,))
    c_rows = cursor.fetchall()
    courses_context = "\n".join([f"[{r[0]}] {r[1]}: {r[2]}" for r in c_rows])

    cursor.execute("SELECT name, objective, description FROM projects WHERE student_id = ?", (student_id,))
    p_rows = cursor.fetchall()
    proj_context = "\n".join([f"Project: {r[0]} | Objective: {r[1]}" for r in p_rows])

    cursor.execute("SELECT category, concept FROM knowledge_history WHERE student_id = ?", (student_id,))
    k_rows = cursor.fetchall()
    knowledge_context = "\n".join([f"{r[0].upper()}: {r[1]}" for r in k_rows])

    response_text = "Offline mode. Configure GEMINI_API_KEY."
    if client:
        try:
            system_prompt = (
                f"You are EMentor, an AI engineering mentor for {session.get('name')}. "
                "Analyze indexed course materials and student projects when answering.\n\n"
                f"Course Materials:\n{courses_context}\n\n"
                f"Projects:\n{proj_context}\n\n"
                f"Knowledge Base:\n{knowledge_context}\n"
            )
            
            contents = [system_prompt, f"Question: {user_message}"]
            
            if screen_capture:
                import base64
                header, encoded = screen_capture.split(",", 1)
                image_bytes = base64.b64decode(encoded)
                contents.append({"mime_type": "image/jpeg", "data": image_bytes})

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
            )
            response_text = response.text

            # Automated knowledge extraction from chat exchange
            ext_prompt = (
                f"Analyze this exchange and identify any technical concept mastered or identified as a knowledge gap.\n"
                f"Student: {user_message}\nMentor: {response_text}\n"
                f"Reply ONLY with 'MASTERED: <concept>' or 'GAP: <concept>' or 'NONE'."
            )
            ext_res = client.models.generate_content(model="gemini-2.5-flash", contents=ext_prompt)
            ext_text = ext_res.text.strip()
            if "MASTERED:" in ext_text:
                concept = ext_text.split("MASTERED:")[1].strip()
                cursor.execute("SELECT 1 FROM knowledge_history WHERE student_id = ? AND concept = ?", (student_id, concept))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO knowledge_history (student_id, category, concept) VALUES (?, 'mastered', ?)", (student_id, concept))
                    conn.commit()
            elif "GAP:" in ext_text:
                concept = ext_text.split("GAP:")[1].strip()
                cursor.execute("SELECT 1 FROM knowledge_history WHERE student_id = ? AND concept = ?", (student_id, concept))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO knowledge_history (student_id, category, concept) VALUES (?, 'gap', ?)", (student_id, concept))
                    conn.commit()

        except Exception as e:
            response_text = f"Error: {str(e)}"

    cursor.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (session_id, 'EMentor', response_text))
    conn.commit()
    conn.close()

    return redirect(url_for('mentor', session=session_id))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)