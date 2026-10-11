import os
import sqlite3
from flask import Flask, render_template_string, request, redirect, session, url_for, flash
from dotenv import load_dotenv
from google import genai

# Load local environment variables if a .env file exists
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configure Gemini API client
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Database Setup
DB_FILE = "ementor.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Students Table for Authentication
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            name TEXT NOT NULL
        )
    ''')
    
    # 2. Chat History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            sender TEXT,
            text TEXT,
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    
    # 3. Course Materials & Knowledge Base Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS course_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL
        )
    ''')
    
    # Insert default test user with realistic Ethiopian university ID format
    cursor.execute("SELECT * FROM students WHERE student_id = 'ETS 1234/15'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO students (student_id, password, name) VALUES (?, ?, ?)", 
                       ('ETS 1234/15', 'password123', 'Yohannes Tadesse'))
        
    # Insert rich initial course materials / knowledge base entries
    cursor.execute("SELECT * FROM course_materials")
    if not cursor.fetchone():
        materials = [
            ('MATH201', 'Applied Mathematics II: Multivariable Calculus', 'Covers multivariable differential calculus, partial derivatives, directional derivatives, gradients, and optimization techniques.'),
            ('MATH201', 'Quadratic Equations & Roots Property', 'For any quadratic equation ax^2 + bx + c = 0, the sum of the roots is given by -b/a and the product of the roots is c/a.'),
            ('ROB101', 'VEX Robotics & Kinematics', 'Differential drive kinematics, two-wheel robot tracking with inverse kinematics, live 2D canvas trajectory rendering, and slip disturbance tracking.')
        ]
        cursor.executemany("INSERT INTO course_materials (course_code, title, content) VALUES (?, ?, ?)", materials)

    conn.commit()
    conn.close()

init_db()

# Modern UI Template with Sidebar & Knowledge Base View
UI_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EMentor AI Platform</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="h-full flex flex-col font-sans">
    {% if not session.get('student_id') %}
    <!-- Login Screen -->
    <div class="flex flex-col items-center justify-center flex-grow px-4">
        <div class="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
            <div class="text-center mb-8">
                <h1 class="text-3xl font-bold tracking-tight text-indigo-400">EMentor Portal</h1>
                <p class="text-sm text-slate-400 mt-2">Sign in with your Student ID and Password</p>
            </div>
            {% with messages = get_flashed_messages() %}
              {% if messages %}
                <div class="mb-4 p-3 bg-red-950/50 border border-red-800 text-red-300 text-sm rounded-xl text-center">
                  {{ messages[0] }}
                </div>
              {% endif %}
            {% endwith %}
            <form method="POST" action="/login" class="space-y-5">
                <div>
                    <label class="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Student ID</label>
                    <input type="text" name="student_id" required placeholder="e.g. ETS 1234/15" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:border-indigo-500 transition">
                </div>
                <div>
                    <label class="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Password</label>
                    <input type="password" name="password" required placeholder="••••••••" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:border-indigo-500 transition">
                </div>
                <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition shadow-lg shadow-indigo-600/20">Sign In</button>
            </form>
        </div>
    </div>
    {% else %}
    <!-- Main App Layout with Sidebar -->
    <div class="flex h-screen overflow-hidden">
        <!-- Sidebar -->
        <aside class="w-64 bg-slate-900 border-r border-slate-800 flex flex-col justify-between p-4 hidden md:flex">
            <div>
                <div class="flex items-center space-x-3 px-2 py-3 mb-6 border-b border-slate-800">
                    <div class="w-3 h-3 bg-emerald-500 rounded-full animate-pulse"></div>
                    <span class="font-bold tracking-wide text-indigo-400">EMentor Core v2.0</span>
                </div>
                <nav class="space-y-2">
                    <a href="/" class="flex items-center space-x-3 px-4 py-3 rounded-xl {{ 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30' if active_tab == 'chat' else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition">
                        <span>💬</span>
                        <span class="font-medium">AI Academic Chat</span>
                    </a>
                    <a href="/materials" class="flex items-center space-x-3 px-4 py-3 rounded-xl {{ 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30' if active_tab == 'materials' else 'text-slate-400 hover:bg-slate-800 hover:text-slate-200' }} transition">
                        <span>📚</span>
                        <span class="font-medium">Course Knowledge Base</span>
                    </a>
                </nav>
            </div>
            <div class="border-t border-slate-800 pt-4 px-2">
                <div class="text-xs text-slate-400 mb-2">Logged in as</div>
                <div class="font-semibold text-slate-200 truncate">{{ session.get('name') }}</div>
                <div class="text-xs text-indigo-400 mb-3">{{ session.get('student_id') }}</div>
                <a href="/logout" class="block text-center text-xs bg-slate-800 hover:bg-slate-700 py-2 rounded-lg transition text-slate-300">Logout</a>
            </div>
        </aside>

        <!-- Content Area -->
        <div class="flex-1 flex flex-col bg-slate-950 overflow-hidden">
            <!-- Mobile Header -->
            <header class="md:hidden border-b border-slate-800 bg-slate-900 px-6 py-4 flex justify-between items-center">
                <span class="font-bold text-indigo-400">EMentor Core</span>
                <div class="flex space-x-3">
                    <a href="/" class="text-sm px-3 py-1 bg-slate-800 rounded">Chat</a>
                    <a href="/materials" class="text-sm px-3 py-1 bg-slate-800 rounded">Materials</a>
                    <a href="/logout" class="text-sm px-3 py-1 bg-red-950 text-red-300 rounded">Logout</a>
                </div>
            </header>

            {% if active_tab == 'chat' %}
            <!-- Chat View -->
            <main class="flex-1 max-w-4xl w-full mx-auto p-4 flex flex-col overflow-hidden">
                <div class="flex-grow overflow-y-auto space-y-4 pr-2 mb-4">
                    <div class="flex justify-start">
                        <div class="bg-slate-900 border border-slate-800 rounded-2xl px-5 py-4 max-w-lg text-slate-300 shadow">
                            Hello! I am your AI academic advisor backed by your course materials and chat history. How can I assist you today?
                        </div>
                    </div>
                    {% for sender, text in history %}
                        <div class="flex {{ 'justify-end' if sender == 'You' else 'justify-start' }}">
                            <div class="{{ 'bg-indigo-600 text-white' if sender == 'You' else 'bg-slate-900 border border-slate-800 text-slate-300' }} rounded-2xl px-5 py-4 max-w-lg shadow whitespace-pre-wrap">
                                {{ text }}
                            </div>
                        </div>
                    {% endfor %}
                </div>

                <form method="POST" action="/chat" class="flex gap-3">
                    <input type="text" name="message" required autocomplete="off" placeholder="Ask about calculus, robotics, or course materials..." class="flex-grow bg-slate-900 border border-slate-800 rounded-xl px-5 py-4 text-slate-100 focus:outline-none focus:border-indigo-500 transition">
                    <button type="submit" class="bg-indigo-600 hover:bg-indigo-500 text-white px-6 rounded-xl font-semibold transition shadow-lg shadow-indigo-600/20">Send</button>
                </form>
            </main>
            {% elif active_tab == 'materials' %}
            <!-- Knowledge Base / Course Materials View -->
            <main class="flex-1 max-w-4xl w-full mx-auto p-6 overflow-y-auto">
                <div class="mb-6">
                    <h2 class="text-2xl font-bold text-slate-100">Course Materials & Knowledge Base</h2>
                    <p class="text-sm text-slate-400 mt-1">Stored modules and references loaded into your persistent database.</p>
                </div>
                <div class="grid gap-4">
                    {% for code, title, content in materials %}
                    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow">
                        <div class="flex items-center justify-between mb-2">
                            <span class="text-xs font-semibold px-2.5 py-1 bg-indigo-950 text-indigo-300 border border-indigo-800 rounded-lg">{{ code }}</span>
                        </div>
                        <h3 class="text-lg font-semibold text-slate-200 mb-2">{{ title }}</h3>
                        <p class="text-sm text-slate-400 leading-relaxed">{{ content }}</p>
                    </div>
                    {% endfor %}
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
def index():
    if 'student_id' not in session:
        return render_template_string(UI_TEMPLATE)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, text FROM messages WHERE student_id = ?", (session['student_id'],))
    history = cursor.fetchall()
    conn.close()
    
    return render_template_string(UI_TEMPLATE, history=history, active_tab='chat')

@app.route("/materials")
def materials():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT course_code, title, content FROM course_materials")
    mat_list = cursor.fetchall()
    conn.close()
    
    return render_template_string(UI_TEMPLATE, materials=mat_list, active_tab='materials')

@app.route("/login", methods=["POST"])
def login():
    student_id = request.form.get("student_id")
    password = request.form.get("password")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name, password FROM students WHERE student_id = ?", (student_id,))
    user = cursor.fetchone()
    conn.close()

    if user and user[1] == password:
        session['student_id'] = student_id
        session['name'] = user[0]
        return redirect(url_for('index'))
    
    flash("Invalid ID or Password. Try ID: ETS 1234/15, Pass: password123")
    return redirect(url_for('index'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route("/chat", methods=["POST"])
def chat():
    if 'student_id' not in session:
        return redirect(url_for('index'))
    
    user_message = request.form.get("message")
    student_id = session['student_id']

    # Save user message
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (student_id, sender, text) VALUES (?, ?, ?)", (student_id, 'You', user_message))
    conn.commit()

    # Fetch knowledge base materials to feed as context to Gemini
    cursor.execute("SELECT course_code, title, content FROM course_materials")
    kb_rows = cursor.fetchall()
    kb_context = "\n".join([f"[{row[0]}] {row[1]}: {row[2]}" for row in kb_rows])

    # Generate Gemini response with Knowledge Base Context
    response_text = "I am running offline. Please configure your GEMINI_API_KEY."
    if client:
        try:
            system_prompt = (
                "You are EMentor, an advanced AI academic advisor for engineering students. "
                "You have access to the following institutional course materials and knowledge base:\n"
                f"{kb_context}\n\n"
                "Use this knowledge to provide precise, helpful academic support to the student."
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{system_prompt}\n\nStudent Question: {user_message}",
            )
            response_text = response.text
        except Exception as e:
            response_text = f"Error generating response: {str(e)}"

    # Save AI response
    cursor.execute("INSERT INTO messages (student_id, sender, text) VALUES (?, ?, ?)", (student_id, 'EMentor', response_text))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

if __name__ == "__main__":
    # Dynamic port binding for local execution and Render compatibility
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)