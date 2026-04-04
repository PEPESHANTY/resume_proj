"""
Streamlit CV Builder — 70/30 layout.
Left (70%): Main workspace with tabs for Knowledge Base, Tailor, Preview.
Right (30%): Chatbot assistant panel.
"""
import os
import streamlit as st
import requests
import json
import time

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

API_URL = os.environ.get("API_URL", "http://localhost:8000")
# On cloud deployment, set API_URL env var to your backend URL.
# e.g. Streamlit Cloud → Settings → Secrets: API_URL = "https://your-backend.com"

# Emails that are pre-authorized to use the server's own API key (no user key needed)
WHITELISTED_EMAILS = {"shantanubhute@gmail.com", "tejaldabhade1511@gmail.com"}

st.set_page_config(
    page_title="CV Builder",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# CUSTOM CSS for 70/30 layout + chat styling
# ─────────────────────────────────────────────

st.markdown("""
<style>
    /* Hide default Streamlit padding */
    .block-container { padding-top: 1rem; padding-bottom: 0; }

    /* Chat container styling */
    .chat-container {
        border-left: 2px solid #e0e0e0;
        padding-left: 1rem;
        height: calc(100vh - 150px);
        overflow-y: auto;
    }
    .chat-msg-user {
        background: #e3f2fd;
        padding: 8px 12px;
        border-radius: 12px 12px 2px 12px;
        margin: 4px 0;
        font-size: 0.9rem;
    }
    .chat-msg-bot {
        background: #f5f5f5;
        padding: 8px 12px;
        border-radius: 12px 12px 12px 2px;
        margin: 4px 0;
        font-size: 0.9rem;
    }

    /* Section cards */
    .kb-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        background: #fafafa;
    }
    .kb-card:hover { background: #f0f0f0; }

    /* Smaller header */
    h1 { font-size: 1.5rem !important; }

    /* Status badges */
    .badge-pass { background: #4caf50; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
    .badge-fail { background: #f44336; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }

    /* PDF preview iframe — full width in right panel */
    .pdf-preview-frame {
        width: 100%;
        height: 600px;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────

def init_state():
    defaults = {
        "authenticated": False,
        "token": None,
        "user_id": None,
        "username": None,
        "user_email": None,
        "openai_api_key": "",       # entered by user in settings; never persisted
        "profile": None,
        "render_config": None,
        "chat_history": [],
        "tailored_data": None,
        "evaluation": None,
        "active_tab": "Knowledge Base",
        "last_docx_path": None,
        "last_pdf_path": None,
        "last_docx_filename": None,
        "last_pdf_filename": None,
        "render_success": False,
        "preview_needs_refresh": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ─────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────

def api_headers():
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    key = st.session_state.get("openai_api_key", "")
    if key:
        headers["x-openai-api-key"] = key
    return headers


def _is_whitelisted():
    return st.session_state.get("user_email") in WHITELISTED_EMAILS


def _needs_api_key():
    """Return True if this user must provide their own OpenAI key."""
    return not _is_whitelisted() and not st.session_state.get("openai_api_key", "")

def api_get(endpoint):
    return requests.get(f"{API_URL}{endpoint}", headers=api_headers())

def api_post(endpoint, data=None, files=None):
    return requests.post(f"{API_URL}{endpoint}", json=data, files=files, headers=api_headers())

def api_put(endpoint, data=None):
    return requests.put(f"{API_URL}{endpoint}", json=data, headers=api_headers())

def load_profile():
    resp = api_get("/profile")
    if resp.status_code == 200:
        body = resp.json()
        st.session_state.profile = body.get("profile")
        st.session_state.render_config = body.get("render_config")


def load_user_email():
    """Fetch the logged-in user's email and store in session state."""
    try:
        resp = requests.get(f"{API_URL}/auth/me", headers=api_headers(), timeout=15)
        if resp.status_code == 200:
            st.session_state.user_email = resp.json().get("email")
    except Exception:
        pass


# ─────────────────────────────────────────────
# LOGIN / REGISTER PAGE
# ─────────────────────────────────────────────

def render_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("📄 CV Builder")
        st.caption("AI-powered ATS-friendly resume builder")
        st.divider()

        tab_login, tab_register = st.tabs(["Login", "Register"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Username or email")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login", use_container_width=True)

                if submit and username and password:
                    try:
                        with st.spinner("Connecting to server (may take up to 60s on first load)..."):
                            resp = requests.post(f"{API_URL}/auth/login",
                                                 data={"username": username, "password": password}, timeout=60)
                        if resp.status_code == 200:
                            body = resp.json()
                            st.session_state.authenticated = True
                            st.session_state.token = body["access_token"]
                            st.session_state.user_id = body["user_id"]
                            st.session_state.username = body["username"]
                            load_profile()
                            load_user_email()
                            st.rerun()
                        else:
                            try:
                                st.error(resp.json().get("detail", "Invalid credentials"))
                            except Exception:
                                st.error(f"Login failed (HTTP {resp.status_code})")
                    except requests.exceptions.ConnectionError:
                        st.error("Cannot reach the backend. Make sure the API server is running.")
                    except requests.exceptions.Timeout:
                        st.error("Server is taking too long to respond. Please try again — it may be waking up.")
                    except Exception as e:
                        st.error(f"Login error: {e}")

        with tab_register:
            with st.form("register_form"):
                new_user = st.text_input("Username")
                new_email = st.text_input("Email")
                new_name = st.text_input("Full name")
                new_pass = st.text_input("Password", type="password")
                reg_submit = st.form_submit_button("Create Account", use_container_width=True)

                if reg_submit and new_user and new_email and new_pass:
                    try:
                        with st.spinner("Connecting to server (may take up to 60s on first load)..."):
                            resp = requests.post(f"{API_URL}/auth/register", json={
                                "username": new_user,
                                "email": new_email,
                                "password": new_pass,
                                "full_name": new_name,
                            }, timeout=60)
                        if resp.status_code == 200:
                            body = resp.json()
                            st.session_state.authenticated = True
                            st.session_state.token = body["access_token"]
                            st.session_state.user_id = body["user_id"]
                            st.session_state.username = body["username"]
                            load_profile()
                            load_user_email()
                            st.rerun()
                        else:
                            try:
                                st.error(resp.json().get("detail", "Registration failed"))
                            except Exception:
                                st.error(f"Registration failed (HTTP {resp.status_code})")
                    except requests.exceptions.ConnectionError:
                        st.error("Cannot reach the backend. Make sure the API server is running on port 8000.")
                    except Exception as e:
                        st.error(f"Registration error: {e}")


# ─────────────────────────────────────────────
# KNOWLEDGE BASE TAB
# ─────────────────────────────────────────────

def render_knowledge_base(profile):
    if not profile:
        st.info("No profile yet. Upload your CV below or use the chatbot to get started.")

        uploaded = st.file_uploader(
            "Upload CV (PDF, DOCX, or Image)",
            type=["pdf", "docx", "doc", "png", "jpg", "jpeg", "webp"],
            key="cv_upload"
        )
        if uploaded:
            with st.spinner("Extracting data from your CV..."):
                files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type)}
                resp = requests.post(f"{API_URL}/upload-cv", files=files, headers=api_headers())

            if resp.status_code == 200:
                body = resp.json()
                load_profile()
                if body.get("questions"):
                    st.warning("Some details are missing:")
                    for q in body["questions"]:
                        st.write(f"• {q}")
                else:
                    st.success("Profile extracted successfully!")
                st.rerun()
            else:
                st.error("Failed to extract CV data.")
        return

    # ── Profile Overview (Editable) ──
    personal = profile.get("personal", {})
    st.subheader(f"👤 {personal.get('name', 'Unknown')}")

    with st.form("personal_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            p_name  = st.text_input("Name", value=personal.get("name", ""), key="p_name")
            p_title = st.text_input("Title / Headline", value=personal.get("title", ""), key="p_title")
            p_email = st.text_input("Email", value=personal.get("email", ""), key="p_email")
            p_loc   = st.text_input("Location", value=personal.get("location", ""), key="p_loc")
        with col_b:
            p_phone = st.text_input("Phone", value=personal.get("phone", ""), key="p_phone")
            links = personal.get("links", {}) or {}
            linkedin = links.get("linkedin", personal.get("linkedin", {})) or {}
            github = links.get("github", personal.get("github", {})) or {}
            p_li_url = st.text_input("LinkedIn URL", value=linkedin.get("url", "") or "", key="p_li")
            p_li_display = st.text_input("LinkedIn Display Text", value=linkedin.get("display", "") or "", key="p_li_disp")
            p_gh_url = st.text_input("GitHub URL", value=github.get("url", "") or "", key="p_gh")
            p_gh_display = st.text_input("GitHub Display Text", value=github.get("display", "") or "", key="p_gh_disp")

        save_personal = st.form_submit_button("💾 Save Personal Info", use_container_width=True)
        if save_personal:
            profile["personal"] = {
                **personal,
                "name": p_name, "title": p_title, "email": p_email,
                "location": p_loc, "phone": p_phone,
                "links": {
                    "linkedin": {"url": p_li_url, "display": p_li_display},
                    "github": {"url": p_gh_url, "display": p_gh_display},
                }
            }
            resp = api_put("/profile", profile)
            if resp.status_code == 200:
                load_profile()
                st.success("Personal info saved!")
                st.rerun()

    st.divider()

    # ── Experience Section ──
    experiences = profile.get("experience", [])
    with st.expander(f"💼 Experience ({len(experiences)} entries)", expanded=True):
        for i, exp in enumerate(experiences):
            active = exp.get("active", True)
            icon = "✅" if active else "❌"
            with st.container():
                col_exp_info, col_exp_toggle = st.columns([9, 1])
                with col_exp_info:
                    st.markdown(f"""<div class="kb-card">
                        <strong>{icon} {exp.get('role', 'Role')}</strong><br>
                        {exp.get('company', '')} | {exp.get('location', '')} | {exp.get('date_range', '')}
                    </div>""", unsafe_allow_html=True)
                with col_exp_toggle:
                    new_active = st.checkbox("Active", value=active, key=f"exp_active_{i}", label_visibility="collapsed")
                    if new_active != active:
                        profile["experience"][i]["active"] = new_active
                        api_put("/profile", profile)
                        load_profile()
                        st.rerun()
                with st.container(border=True):
                    st.caption(f"✏️ Edit bullets — {exp.get('role', 'Role')}")
                    for j, b in enumerate(exp.get("bullets", [])):
                        new_b = st.text_area(f"Bullet {j+1}", value=b, key=f"exp_{i}_bul_{j}", height=100)
                        if new_b != b:
                            profile["experience"][i]["bullets"][j] = new_b
                    if st.button(f"💾 Save bullets", key=f"save_exp_bul_{i}"):
                        api_put("/profile", profile)
                        load_profile()
                        st.success("Bullets saved!")

    # ── Projects Section ──
    projects = profile.get("projects", [])
    with st.expander(f"🚀 Projects ({len(projects)} entries)", expanded=True):
        for i, proj in enumerate(projects):
            active = proj.get("active", True)
            icon = "✅" if active else "❌"
            col_proj_info, col_proj_toggle = st.columns([9, 1])
            with col_proj_info:
                st.markdown(f"""<div class="kb-card">
                    <strong>{icon} {proj.get('title', 'Project')}</strong> | {proj.get('date', '')}<br>
                    <em>{proj.get('tech', '')}</em>
                </div>""", unsafe_allow_html=True)
            with col_proj_toggle:
                new_active = st.checkbox("Active", value=active, key=f"proj_active_{i}", label_visibility="collapsed")
                if new_active != active:
                    profile["projects"][i]["active"] = new_active
                    api_put("/profile", profile)
                    load_profile()
                    st.rerun()
            with st.container(border=True):
                st.caption(f"✏️ Edit bullets — {proj.get('title', 'Project')}")
                for j, b in enumerate(proj.get("bullets", [])):
                    new_b = st.text_area(f"Bullet {j+1}", value=b, key=f"proj_{i}_bul_{j}", height=100)
                    if new_b != b:
                        profile["projects"][i]["bullets"][j] = new_b
                if st.button(f"💾 Save", key=f"save_proj_{i}"):
                    api_put("/profile", profile)
                    load_profile()
                    st.success("Saved!")

    # ── Skills Section ──
    skills = profile.get("skills_pool", profile.get("skills", {}).get("full", []))
    with st.expander(f"🛠️ Skills ({len(skills)} categories)"):
        for i, s in enumerate(skills):
            cat = s.get("category", "")
            items = s.get("items", "")
            if isinstance(items, list):
                items = ", ".join(items)
            new_items = st.text_input(f"**{cat}**", value=items, key=f"skill_{i}")
            if new_items != items:
                if "skills_pool" in profile:
                    profile["skills_pool"][i]["items"] = new_items
                elif "skills" in profile and "full" in profile["skills"]:
                    profile["skills"]["full"][i]["items"] = new_items
        if st.button("💾 Save Skills", key="save_skills"):
            api_put("/profile", profile)
            load_profile()
            st.success("Skills saved!")

    # ── Certifications (with links) ──
    certs = profile.get("certifications", [])
    with st.expander(f"🏆 Certifications ({len(certs)})"):
        for i, c in enumerate(certs):
            col_c1, col_c2, col_c3 = st.columns([4, 2, 2])
            with col_c1:
                new_name = st.text_input("Name", value=c.get("name", ""), key=f"cert_name_{i}")
            with col_c2:
                new_date = st.text_input("Date", value=c.get("date", ""), key=f"cert_date_{i}")
            with col_c3:
                new_link_text = st.text_input("Link Text", value=c.get("link_text", ""), key=f"cert_lt_{i}",
                                              help="The word(s) in the name to hyperlink")
            new_url = st.text_input("URL", value=c.get("url", "") or "", key=f"cert_url_{i}",
                                    help="Certification/badge URL")
            if any([new_name != c.get("name", ""), new_date != c.get("date", ""),
                    new_link_text != c.get("link_text", ""), new_url != (c.get("url", "") or "")]):
                profile["certifications"][i].update({
                    "name": new_name, "date": new_date,
                    "link_text": new_link_text, "url": new_url or None
                })
            if i < len(certs) - 1:
                st.divider()
        if st.button("💾 Save Certifications", key="save_certs"):
            api_put("/profile", profile)
            load_profile()
            st.success("Certifications saved!")

    # ── Education (with honors + grade) ──
    edu = profile.get("education", [])
    with st.expander(f"🎓 Education ({len(edu)})"):
        for i, e in enumerate(edu):
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                new_degree = st.text_input("Degree", value=e.get("degree", ""), key=f"edu_deg_{i}")
                new_inst   = st.text_input("Institution", value=e.get("institution", ""), key=f"edu_inst_{i}")
                new_honors = st.text_input("Honours", value=e.get("honors", "") or "", key=f"edu_hon_{i}",
                                           help="e.g., First Class with Honours (1:1)")
            with col_e2:
                new_date  = st.text_input("Date", value=e.get("date", ""), key=f"edu_date_{i}")
                new_grade = st.text_input("Grade", value=e.get("grade", "") or "", key=f"edu_grade_{i}",
                                          help="e.g., CGPA: 8.97/10")
                new_modules = st.text_input("Modules", value=e.get("modules", "") or "", key=f"edu_mod_{i}",
                                            help="Comma-separated or newline-separated")
            if any([new_degree != e.get("degree", ""), new_inst != e.get("institution", ""),
                    new_honors != (e.get("honors", "") or ""), new_date != e.get("date", ""),
                    new_grade != (e.get("grade", "") or ""), new_modules != (e.get("modules", "") or "")]):
                profile["education"][i].update({
                    "degree": new_degree, "institution": new_inst,
                    "honors": new_honors or None, "date": new_date,
                    "grade": new_grade or None, "modules": new_modules or None,
                })
            if i < len(edu) - 1:
                st.divider()
        if st.button("💾 Save Education", key="save_edu"):
            api_put("/profile", profile)
            load_profile()
            st.success("Education saved!")

    # ── Extracurricular ──
    extras = profile.get("extracurricular", [])
    with st.expander(f"🌟 Extracurricular ({len(extras)})"):
        for i, ex in enumerate(extras):
            new_text = st.text_area(
                f"Activity {i+1}",
                value=ex.get("text", ""),
                height=68,
                key=f"extra_text_{i}"
            )
            if new_text != ex.get("text", ""):
                profile["extracurricular"][i]["text"] = new_text
            if i < len(extras) - 1:
                st.divider()

        # Add new item
        new_extra = st.text_input("Add new extracurricular activity", key="new_extra_input",
                                  placeholder="e.g., Volunteered at Simon Community; led plantation drives")
        if new_extra and st.button("➕ Add Activity", key="add_extra_btn"):
            if "extracurricular" not in profile:
                profile["extracurricular"] = []
            new_id = f"extra_{len(profile['extracurricular']) + 1}"
            profile["extracurricular"].append({"id": new_id, "text": new_extra, "active": True})
            api_put("/profile", profile)
            load_profile()
            st.success("Activity added!")
            st.rerun()

        if st.button("💾 Save Extracurricular", key="save_extras"):
            api_put("/profile", profile)
            load_profile()
            st.success("Extracurricular saved!")

    # ── Upload new / Update ──
    st.divider()
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        uploaded = st.file_uploader(
            "Upload new/updated CV (merges with existing)",
            type=["pdf", "docx", "doc", "png", "jpg", "jpeg"],
            key="cv_upload_update"
        )
        if uploaded:
            with st.spinner("Merging new data..."):
                files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type)}
                resp = requests.post(f"{API_URL}/upload-cv", files=files, headers=api_headers())
            if resp.status_code == 200:
                load_profile()
                st.success("Profile updated!")
                st.rerun()

    with col_u2:
        img = st.file_uploader(
            "Upload image for reference (OCR)",
            type=["png", "jpg", "jpeg", "webp"],
            key="img_ref"
        )
        if img:
            with st.spinner("Reading image..."):
                files = {"file": (img.name, img.getvalue(), img.type)}
                resp = requests.post(f"{API_URL}/read-image", files=files,
                                     data={"context": "Extract text"}, headers=api_headers())
            if resp.status_code == 200:
                st.text_area("Extracted text:", resp.json().get("text", ""), height=200)


# ─────────────────────────────────────────────
# TAILOR TAB (paste JD, run pipeline)
# ─────────────────────────────────────────────

def render_tailor_tab(profile):
    if not profile:
        st.warning("Upload your CV first in the Knowledge Base tab.")
        return

    st.subheader("🎯 Tailor CV for a Job")

    jd = st.text_area("Paste the Job Description here:", height=200, key="jd_input")

    col1, col2, col3 = st.columns(3)
    with col1:
        mode = st.selectbox("CV Mode", ["2page", "1page"], key="tailor_mode")
    with col2:
        company = st.text_input("Company Short Name", value="GENERIC", key="tailor_company")
    with col3:
        st.write("")
        st.write("")
        run_btn = st.button("🚀 Generate Tailored CV", use_container_width=True, type="primary")

    if run_btn and jd:
        with st.spinner("Running Tailor → Evaluate → Auto-iterate pipeline..."):
            resp = api_post("/tailor", {
                "job_description": jd,
                "mode": mode,
                "company": company,
            })

        if resp.status_code == 200:
            body = resp.json()
            st.session_state.evaluation = body.get("evaluation")
            st.session_state.tailored_data = True
            st.session_state.saved_company = company
            st.session_state.saved_jd = jd
            st.session_state.saved_mode = mode
            st.session_state.needs_manual_review = body.get("needs_manual_review", False)
            st.session_state.keyword_coverage = body.get("keyword_coverage", {})

            # Show evaluation
            verdict = body.get("verdict", "FAIL")
            score = body.get("evaluation", {}).get("overall_score", 0)
            threshold = body.get("pass_threshold", 95)

            if verdict == "PASS":
                st.success(f"✅ PASS — Score: {score}/100 (threshold: {threshold}) after {body.get('iterations', 1)} iteration(s)")
            else:
                st.warning(f"⚠️ Below threshold — Score: {score}/100 (need ≥{threshold}) after {body.get('iterations', 1)} auto-iteration(s)")
                st.info("You can manually improve it below, or render as-is.")

            _render_eval_details(body)
            st.rerun()

        else:
            st.error(f"Pipeline failed: {resp.json().get('detail', 'Unknown error')}")

    # ── Show persistent evaluation results + manual controls ──
    if st.session_state.get("evaluation"):
        evaluation = st.session_state.evaluation
        score = evaluation.get("overall_score", 0)
        verdict = evaluation.get("verdict", "FAIL")

        st.divider()
        st.subheader("📊 Current Evaluation")

        if verdict == "PASS":
            st.success(f"✅ PASS — Score: {score}/100")
        else:
            st.warning(f"⚠️ Score: {score}/100 (need ≥95 to auto-pass)")

        # Score breakdown
        scores = evaluation.get("scores", {})
        if scores:
            st.write("**Score Breakdown:**")
            for dim, val in scores.items():
                st.progress(val / 100, text=f"{dim.replace('_', ' ').title()}: {val}/100")

        # Feedback
        feedback = evaluation.get("feedback", "")
        if feedback:
            with st.expander("📝 Detailed Feedback", expanded=(verdict != "PASS")):
                st.write(feedback)
                issues = evaluation.get("issues", [])
                if issues:
                    st.write("**Issues:**")
                    for issue in issues:
                        st.write(f"• {issue}")
                strengths = evaluation.get("strengths", [])
                if strengths:
                    st.write("**Strengths:**")
                    for s in strengths:
                        st.write(f"✓ {s}")

        # ── Missing Keywords — Tickable selection ──
        kw_coverage = st.session_state.get("keyword_coverage", {})
        missed = kw_coverage.get("missed", [])
        matched = kw_coverage.get("matched", [])

        if matched:
            with st.expander(f"✅ Matched Keywords ({len(matched)})"):
                st.write(", ".join(matched))

        if missed:
            with st.expander(f"⚠️ Missing Keywords ({len(missed)}) — Select to inject", expanded=True):
                st.caption("Tick the keywords you want added. They'll be smartly placed into Skills or Experience bullets.")
                selected_keywords = []
                cols = st.columns(3)
                for i, kw in enumerate(missed):
                    with cols[i % 3]:
                        if st.checkbox(kw, key=f"kw_{i}", value=True):
                            selected_keywords.append(kw)

                if selected_keywords and st.button("💉 Inject Selected Keywords", type="primary"):
                    with st.spinner(f"Injecting {len(selected_keywords)} keywords..."):
                        resp = api_post("/inject-keywords", {
                            "company": st.session_state.get("saved_company", "GENERIC"),
                            "keywords": selected_keywords,
                            "job_description": st.session_state.get("saved_jd", ""),
                        })
                    if resp.status_code == 200:
                        st.success(f"Injected: {', '.join(selected_keywords)}")
                        st.info("Click 'Re-evaluate' below to check the new score.")
                    else:
                        st.error("Injection failed.")

        # ── Manual Iteration Controls ──
        if st.session_state.get("needs_manual_review") or verdict != "PASS":
            st.divider()
            st.subheader("🔄 Manual Improvement")
            st.caption("Provide specific feedback to improve the tailored CV, or re-evaluate after keyword injection.")

            col_re1, col_re2 = st.columns(2)

            with col_re1:
                manual_feedback = st.text_area(
                    "Your feedback (optional — specific instructions for improvement):",
                    height=100,
                    key="manual_feedback",
                    placeholder="e.g., 'Emphasize more cloud computing experience', 'Move Python higher in skills'"
                )

                if st.button("🔄 Re-tailor with Feedback", use_container_width=True):
                    with st.spinner("Re-tailoring..."):
                        resp = api_post("/re-tailor", {
                            "company": st.session_state.get("saved_company", "GENERIC"),
                            "job_description": st.session_state.get("saved_jd", ""),
                            "feedback": manual_feedback or evaluation.get("feedback", ""),
                            "mode": st.session_state.get("saved_mode", "2page"),
                        })
                    if resp.status_code == 200:
                        body = resp.json()
                        st.session_state.evaluation = body.get("evaluation")
                        new_score = body.get("evaluation", {}).get("overall_score", 0)
                        st.session_state.keyword_coverage = body.get("keyword_coverage", kw_coverage)
                        if body.get("verdict") == "PASS":
                            st.session_state.needs_manual_review = False
                            st.success(f"✅ Improved to {new_score}/100 — PASS!")
                        else:
                            st.warning(f"Score now: {new_score}/100 — keep iterating or render as-is.")
                        st.rerun()
                    else:
                        st.error("Re-tailor failed.")

            with col_re2:
                st.write("")
                st.write("")
                if st.button("🔍 Re-evaluate Only", use_container_width=True,
                             help="Re-run evaluation on current CV without re-tailoring"):
                    with st.spinner("Evaluating..."):
                        profile_data = st.session_state.profile
                        resp_profile = api_get("/profile")
                        if resp_profile.status_code == 200:
                            profile_data = resp_profile.json().get("profile", profile_data)
                        # Load current tailored data via re-tailor with empty feedback
                        resp = api_post("/re-tailor", {
                            "company": st.session_state.get("saved_company", "GENERIC"),
                            "job_description": st.session_state.get("saved_jd", ""),
                            "feedback": "No changes needed. Just re-evaluate the current version.",
                            "mode": st.session_state.get("saved_mode", "2page"),
                        })
                    if resp.status_code == 200:
                        body = resp.json()
                        st.session_state.evaluation = body.get("evaluation")
                        st.session_state.keyword_coverage = body.get("keyword_coverage", kw_coverage)
                        new_score = body.get("evaluation", {}).get("overall_score", 0)
                        if body.get("verdict") == "PASS":
                            st.session_state.needs_manual_review = False
                        st.info(f"Re-evaluated: {new_score}/100")
                        st.rerun()

        # ── Render button ──
        st.divider()
        if st.button("📄 Render & Preview", use_container_width=True, type="primary"):
            with st.spinner("Rendering CV..."):
                render_resp = api_post("/render", {
                    "mode": st.session_state.get("saved_mode", "2page"),
                    "company": st.session_state.get("saved_company", "GENERIC"),
                    "export_pdf": True,
                })
            if render_resp.status_code == 200:
                render_body = render_resp.json()
                st.session_state.last_docx_path = render_body.get("docx_path")
                st.session_state.last_pdf_path = render_body.get("pdf_path")
                st.session_state.last_docx_filename = render_body.get("docx_filename")
                st.session_state.last_pdf_filename = render_body.get("pdf_filename")
                st.session_state.render_success = True
                st.session_state.preview_needs_refresh = False
                st.success("CV rendered! Check the Preview panel on the right. →")
                st.rerun()
            else:
                try:
                    detail = render_resp.json().get("detail", "Unknown error")
                except Exception:
                    detail = f"HTTP {render_resp.status_code}"
                st.error(f"Render failed: {detail}")


def _render_eval_details(body):
    """Helper to store eval details in session — display handled by persistent section."""
    pass


# ─────────────────────────────────────────────
# SHARED DOWNLOAD + PREVIEW HELPER
# ─────────────────────────────────────────────

def _show_download_and_preview(context="main"):
    """Show download buttons and HTML preview of the rendered CV."""
    docx_filename = st.session_state.get("last_docx_filename")
    pdf_filename = st.session_state.get("last_pdf_filename")
    docx_path = st.session_state.get("last_docx_path")
    pdf_path = st.session_state.get("last_pdf_path")

    if not docx_filename and not pdf_filename:
        import os
        if docx_path:
            docx_filename = os.path.basename(docx_path)
        if pdf_path:
            pdf_filename = os.path.basename(pdf_path)

    if not docx_filename and not pdf_filename:
        st.caption("No rendered CV yet. Render from the Tailor tab or click 🔄 Refresh Preview.")
        return

    # Download buttons
    col_d1, col_d2 = st.columns(2)

    if docx_filename:
        with col_d1:
            try:
                resp = requests.get(
                    f"{API_URL}/download/{docx_filename}",
                    headers=api_headers(),
                    timeout=30,
                )
                if resp.status_code == 200:
                    st.download_button(
                        "⬇️ DOCX",
                        data=resp.content,
                        file_name=docx_filename,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        key=f"dl_docx_{context}",
                    )
                else:
                    st.warning("DOCX not ready.")
            except Exception as e:
                st.warning(f"DOCX error: {e}")

    if pdf_filename:
        with col_d2:
            try:
                resp = requests.get(
                    f"{API_URL}/download/{pdf_filename}",
                    headers=api_headers(),
                    timeout=30,
                )
                if resp.status_code == 200:
                    st.download_button(
                        "⬇️ PDF",
                        data=resp.content,
                        file_name=pdf_filename,
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"dl_pdf_{context}",
                    )
                else:
                    st.warning("PDF not ready.")
            except Exception as e:
                st.warning(f"PDF error: {e}")

    # HTML preview — FULL WIDTH (mammoth converts docx → HTML server-side)
    if docx_filename:
        try:
            prev_resp = requests.get(
                f"{API_URL}/preview/{docx_filename}",
                headers=api_headers(),
                timeout=30,
            )
            if prev_resp.status_code == 200:
                import base64
                b64 = base64.b64encode(prev_resp.content).decode("utf-8")
                st.markdown(
                    f'<iframe src="data:text/html;base64,{b64}" '
                    f'class="pdf-preview-frame"></iframe>',
                    unsafe_allow_html=True,
                )
        except Exception:
            pass  # Preview is best-effort; download buttons are the primary action


# ─────────────────────────────────────────────
# CHATBOT PANEL (right 30%)
# ─────────────────────────────────────────────

def _do_render_preview():
    """Trigger a render and store file info in session state."""
    mode = st.session_state.get("saved_mode", "2page")
    company = st.session_state.get("saved_company", "GENERIC")
    resp = api_post("/render", {
        "mode": mode,
        "company": company,
        "export_pdf": True,
    })
    if resp.status_code == 200:
        body = resp.json()
        st.session_state.last_docx_path = body.get("docx_path")
        st.session_state.last_pdf_path = body.get("pdf_path")
        st.session_state.last_docx_filename = body.get("docx_filename")
        st.session_state.last_pdf_filename = body.get("pdf_filename")
        st.session_state.render_success = True
        return True
    return False


def render_chatbot():
    st.markdown("### 💬 Assistant")
    st.caption("Ask me to edit your profile, change formatting, or anything else.")

    # Chat history display
    chat_container = st.container(height=350)
    with chat_container:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-msg-user">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-msg-bot">{msg["content"]}</div>', unsafe_allow_html=True)

    # Chat input
    user_input = st.chat_input("Type a message...", key="chat_input")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        if st.session_state.authenticated:
            resp = api_post("/chat", {
                "message": user_input,
                "chat_history": st.session_state.chat_history[-10:],
                "company": st.session_state.get("saved_company", "GENERIC"),
            })
            if resp.status_code == 200:
                body = resp.json()
                reply = body.get("reply", "Sorry, something went wrong.")
                st.session_state.chat_history.append({"role": "assistant", "content": reply})

                if body.get("data_updated") or body.get("needs_re_render"):
                    load_profile()
                    st.session_state.preview_needs_refresh = True
            else:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": "⚠️ Could not reach the server."
                })
        else:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": "Please login first to use the assistant."
            })

        st.rerun()

    # File upload for chat (CV files + images)
    with st.expander("📎 Upload file (CV or image)"):
        chat_file = st.file_uploader("", type=["pdf", "docx", "doc", "png", "jpg", "jpeg", "webp"], key="chat_file",
                               label_visibility="collapsed")
        if chat_file:
            fname = chat_file.name.lower()
            if fname.endswith((".pdf", ".docx", ".doc")):
                with st.spinner("Extracting CV data..."):
                    files = {"file": (chat_file.name, chat_file.getvalue(), chat_file.type)}
                    resp = requests.post(f"{API_URL}/upload-cv", files=files, headers=api_headers())
                if resp.status_code == 200:
                    load_profile()
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"✅ Extracted data from **{chat_file.name}** and updated your knowledge base."
                    })
                    st.session_state.preview_needs_refresh = True
                    st.rerun()
                else:
                    st.error("Failed to extract CV data.")
            else:
                with st.spinner("Reading image..."):
                    files = {"file": (chat_file.name, chat_file.getvalue(), chat_file.type)}
                    resp = requests.post(f"{API_URL}/read-image", files=files,
                                         data={"context": "Extract text"}, headers=api_headers())
                if resp.status_code == 200:
                    text = resp.json().get("text", "")
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"📷 Extracted from image:\n\n{text[:500]}..."
                    })
                    st.rerun()


def render_preview_panel():
    """Preview panel shown below the chatbot on the right side."""
    st.divider()
    st.markdown("##### 👁️ Preview")

    # Refresh preview button — prominent when data changed
    if st.session_state.get("preview_needs_refresh"):
        if st.button("🔄 Refresh Preview", use_container_width=True, type="primary",
                     key="refresh_preview_btn"):
            with st.spinner("Re-rendering..."):
                if _do_render_preview():
                    st.session_state.preview_needs_refresh = False
                    st.rerun()
                else:
                    st.error("Render failed.")
    else:
        if st.button("🔄 Refresh Preview", use_container_width=True, key="refresh_preview_btn_normal"):
            with st.spinner("Rendering..."):
                if _do_render_preview():
                    st.rerun()
                else:
                    st.error("Render failed.")

    _show_download_and_preview(context="sidebar")


# ─────────────────────────────────────────────
# SAVED CVs TAB
# ─────────────────────────────────────────────

def render_saved_cvs_tab():
    st.subheader("📁 Saved CVs")
    st.caption("All previously rendered CVs — one card per company/role. Click to preview or download.")

    if st.button("🔄 Refresh List", key="refresh_saved_cvs"):
        if "saved_cvs_cache" in st.session_state:
            del st.session_state["saved_cvs_cache"]
        st.rerun()

    # Load list (cached in session to avoid repeated API calls)
    if "saved_cvs_cache" not in st.session_state:
        resp = api_get("/saved-cvs")
        if resp.status_code == 200:
            st.session_state.saved_cvs_cache = resp.json().get("saved_cvs", [])
        else:
            st.error("Could not load saved CVs.")
            return

    saved = st.session_state.saved_cvs_cache
    if not saved:
        st.info("No saved CVs yet. Tailor a CV and click Render to create one.")
        return

    st.caption(f"{len(saved)} saved CV(s) found.")

    for cv in saved:
        company = cv.get("company", "?")
        mode = cv.get("mode", "2page")
        docx_fn = cv.get("docx_filename")
        pdf_fn = cv.get("pdf_filename")
        label = f"**{company}** — {mode.upper()}"

        with st.expander(label, expanded=False):
            col_d, col_p, col_prev = st.columns([1, 1, 2])

            with col_d:
                if docx_fn:
                    try:
                        r = requests.get(f"{API_URL}/download/{docx_fn}",
                                         headers=api_headers(), timeout=30)
                        if r.status_code == 200:
                            st.download_button(
                                "⬇️ DOCX",
                                data=r.content,
                                file_name=docx_fn,
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True,
                                key=f"dl_docx_{company}_{mode}",
                            )
                    except Exception:
                        st.warning("DOCX unavailable")
                else:
                    st.caption("No DOCX")

            with col_p:
                if pdf_fn:
                    try:
                        r = requests.get(f"{API_URL}/download/{pdf_fn}",
                                         headers=api_headers(), timeout=30)
                        if r.status_code == 200:
                            st.download_button(
                                "⬇️ PDF",
                                data=r.content,
                                file_name=pdf_fn,
                                mime="application/pdf",
                                use_container_width=True,
                                key=f"dl_pdf_{company}_{mode}",
                            )
                    except Exception:
                        st.warning("PDF unavailable")
                else:
                    st.caption("No PDF")

            with col_prev:
                # Inline preview button — loads on demand to keep UI fast
                preview_key = f"preview_open_{company}_{mode}"
                if st.button("👁️ Preview", key=f"btn_prev_{company}_{mode}", use_container_width=True):
                    st.session_state[preview_key] = not st.session_state.get(preview_key, False)

            if st.session_state.get(preview_key) and docx_fn:
                try:
                    import base64
                    prev_r = requests.get(f"{API_URL}/preview/{docx_fn}",
                                          headers=api_headers(), timeout=30)
                    if prev_r.status_code == 200:
                        b64 = base64.b64encode(prev_r.content).decode("utf-8")
                        st.markdown(
                            f'<iframe src="data:text/html;base64,{b64}" '
                            f'class="pdf-preview-frame"></iframe>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.warning("Preview not available.")
                except Exception as e:
                    st.warning(f"Preview error: {e}")


# ─────────────────────────────────────────────
# MAIN LAYOUT
# ─────────────────────────────────────────────

def main():
    if not st.session_state.authenticated:
        render_login()
        return

    # Top bar
    top_left, top_right = st.columns([8, 2])
    with top_left:
        st.title("📄 CV Builder")
    with top_right:
        st.write(f"👤 {st.session_state.username}")
        if st.button("Logout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    st.divider()

    # ── API key warning banner ──
    if _needs_api_key():
        st.warning(
            "**API key required.** AI features (chat, CV tailoring, CV upload) are disabled. "
            "Go to **Settings** → **OpenAI API Key** to enter your key. It's stored in your browser session only.",
            icon="🔑",
        )

    # ── 70/30 LAYOUT ──
    main_col, chat_col = st.columns([55, 45])

    # LEFT 70% — Main workspace
    with main_col:
        tab_kb, tab_tailor, tab_saved, tab_settings = st.tabs([
            "📋 Knowledge Base",
            "🎯 Tailor CV",
            "📁 Saved CVs",
            "⚙️ Settings",
        ])

        with tab_kb:
            render_knowledge_base(st.session_state.profile)

        with tab_tailor:
            render_tailor_tab(st.session_state.profile)

        with tab_saved:
            render_saved_cvs_tab()

        with tab_settings:
            # ── API Key (non-whitelisted users only) ──────────────
            if not _is_whitelisted():
                st.subheader("🔑 OpenAI API Key")
                st.caption(
                    "Enter your own OpenAI API key to use AI features (chat edits, tailoring, CV extraction). "
                    "The key is stored in your browser session only and is never saved to any server."
                )
                key_input = st.text_input(
                    "OpenAI API Key",
                    value=st.session_state.get("openai_api_key", ""),
                    type="password",
                    placeholder="sk-...",
                    key="api_key_input",
                )
                col_save, col_clear = st.columns([1, 1])
                with col_save:
                    if st.button("Save Key", use_container_width=True, type="primary"):
                        st.session_state.openai_api_key = key_input.strip()
                        if st.session_state.openai_api_key:
                            st.success("API key saved for this session.")
                        else:
                            st.warning("Key cleared.")
                with col_clear:
                    if st.button("Clear Key", use_container_width=True):
                        st.session_state.openai_api_key = ""
                        st.info("Key cleared.")
                if st.session_state.get("openai_api_key"):
                    st.success("API key is set — AI features are enabled.")
                else:
                    st.warning("No API key set. AI features (chat, tailoring, CV upload) will be blocked until you enter a key.")
                st.divider()

            st.subheader("⚙️ Render Configuration")
            config = st.session_state.render_config or {}

            with st.form("config_form"):
                col1, col2 = st.columns(2)
                with col1:
                    font_name = st.selectbox("Font", ["Calibri", "Arial", "Times New Roman", "Garamond", "Helvetica"],
                                             index=0, key="cfg_font")
                    font_size = st.number_input("Font Size", 8, 14, int(config.get("font_size", 10)), key="cfg_fsize")
                    page_size = st.selectbox("Page Size", ["letter", "a4"],
                                             index=0 if config.get("page_size") == "letter" else 1, key="cfg_page")
                with col2:
                    inc_summary = st.checkbox("Include Summary", value=config.get("include_summary", True), key="cfg_sum")
                    inc_extra = st.checkbox("Include Extracurricular", value=config.get("include_extracurricular", True), key="cfg_extra")
                    max_certs = st.number_input("Max Certs (1-page)", 1, 10, config.get("max_certs_1page", 4), key="cfg_certs")

                section_order = st.multiselect(
                    "Section Order (drag to reorder)",
                    ["summary", "skills", "education", "certifications", "experience", "projects", "extracurricular"],
                    default=config.get("section_order",
                                       ["summary", "skills", "education", "certifications", "experience", "projects", "extracurricular"]),
                    key="cfg_order"
                )

                save_cfg = st.form_submit_button("Save Settings", use_container_width=True)
                if save_cfg:
                    new_config = {
                        "font_name": font_name,
                        "font_size": font_size,
                        "page_size": page_size,
                        "include_summary": inc_summary,
                        "include_extracurricular": inc_extra,
                        "max_certs_1page": max_certs,
                        "section_order": section_order,
                    }
                    resp = api_put("/render-config", new_config)
                    if resp.status_code == 200:
                        st.session_state.render_config = resp.json().get("config", new_config)
                        st.success("Settings saved!")

    # RIGHT 30% — Chatbot + Preview
    with chat_col:
        render_chatbot()
        render_preview_panel()


if __name__ == "__main__":
    main()
