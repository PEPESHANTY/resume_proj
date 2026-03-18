# CLAUDE.md — Shantanu Bhute: Resume Content Library

**Purpose:** Reusable content bank for rapid resume tailoring. When a new job description is provided:
1. Read the JD carefully
2. Copy the appropriate generic master template (`SHANTANU_CV_GENERIC_2PAGE.md` or `SHANTANU_CV_GENERIC_1PAGE.md`)
3. Rename as `SHANTANU_CV_<COMPANY_SHORT>` (e.g., `SHANTANU_CV_MS`, `SHANTANU_CV_AMZN`)
4. Swap in variants from this file that best match the JD keywords and role focus
5. Reorder bullets by relevance — most relevant first

---

## FILE STRUCTURE

| File / Folder | Purpose |
|---|---|
| `SHANTANU_CV_GENERIC_2PAGE.md` | Full 2-page master template (Markdown) |
| `SHANTANU_CV_GENERIC_1PAGE.md` | Condensed 1-page master template (Markdown) |
| `CREATED/SHANTANU_CV_GENERIC_2PAGE.docx` | Full 2-page master — formatted Word document |
| `CREATED/SHANTANU_CV_GENERIC_1PAGE.docx` | Condensed 1-page master — formatted Word document |
| `build_cv.py` | Python script to regenerate/rebuild all .docx files from content defined in the script |
| `CLAUDE.md` | This file — reusable content library |

**Reference files (NOT Shantanu's content — formatting inspiration only):**
- `Deepesh Bathija Resume.docx` — used as style/format reference
- `Deepesh Bathija CV.pdf` — format reference
- `Puru Chaudhary Software Engineer CV.pdf` — format reference

### How to produce a company-specific .docx:
1. Edit `build_cv.py` — swap bullet variants using this CLAUDE.md as reference
2. Change output filename in the script to `SHANTANU_CV_<COMPANY_SHORT>.docx`
3. Run `python build_cv.py` from the `d:/A RESUMES/` folder
4. Output goes to `CREATED/` folder automatically

**Rule:** Never overwrite master templates. Always create a named copy for company-specific versions.

---

## CANDIDATE SNAPSHOT

- **Name:** Shantanu Bhute
- **Location:** Dublin 04, Ireland
- **Email:** shantanubhute@gmail.com | **Phone:** +353 899476612
- **Education:** MSc Computer Science, UCD (First Class Honours, 2024–2025) + BE CS (AI-ML), SPPU (CGPA 8.97, 2019–2023)
- **Core strengths:** RAG/LLM engineering, ML pipeline development, data engineering, Python/SQL/Java, AWS, NLP, Computer Vision
- **Best-fit roles:** Data Scientist, ML Engineer, AI Engineer, Data Analyst, Software Engineer (Data/AI focus), Research Engineer

---

## TITLE / HEADLINE VARIANTS

| Role Focus | Headline |
|---|---|
| Generic / Broad | Data Scientist \| AI/ML Engineer \| Software Engineer |
| AI/LLM-focused | AI/ML Engineer \| LLM & RAG Systems \| Data Scientist |
| Data-focused | Data Scientist \| ML Engineer \| Python & SQL Specialist |
| Analytics-focused | Data Analyst \| Business Intelligence \| Python & SQL |
| Software Engineering | Software Engineer \| AI/ML \| Python & Java |
| Research | AI Research Engineer \| NLP \| Computer Vision |

---

## PROFESSIONAL SUMMARY VARIANTS

### Generic (default)
> MSc Computer Science graduate (UCD, First Class Honours) with hands-on experience in data science, machine learning, and AI engineering. Skilled in building end-to-end ML pipelines, RAG systems, and LLM-integrated applications. Proficient in Python, SQL, Java, and cloud platforms (AWS, Azure). Proven ability to deliver scalable, production-ready solutions across data engineering, NLP, and computer vision domains.

### AI/LLM-Focused
> MSc Computer Science graduate (UCD) with deep hands-on experience in LLM applications, RAG pipelines, and production AI systems. Proficient in LangChain, OpenAI, Hugging Face, and vector databases (Qdrant, FAISS). Experienced in prompt engineering, evaluation (RAGAS), and deploying AI systems that are multilingual, citation-aware, and scalable.

### Data Science / Analytics-Focused
> MSc Computer Science graduate (UCD, First Class Honours) with strong foundations in statistical modelling, data wrangling, and machine learning. Experienced building end-to-end data science workflows in Python and R, with exposure to business intelligence (Power BI), cloud platforms (AWS), and cross-functional stakeholder communication.

### Software Engineering (Data/AI)
> MSc Computer Science graduate (UCD) with 2+ years of experience in software engineering, backend development, and AI integration. Skilled in Python, Java, SQL, and Spring Boot. Experienced building data validation systems, API-integrated AI modules, and cloud-deployed pipelines on AWS.

### Business/Product-Focused
> MSc Computer Science graduate with experience translating business problems into data-driven solutions. Delivered AI-powered tools including CRM chatbots, knowledge retrieval systems, and automated pipelines — improving prediction accuracy, reducing manual effort, and enabling actionable insights for stakeholders.

### 1-Page Short (default)
> MSc Computer Science (UCD, First Class Honours) with experience in data science, ML pipelines, RAG systems, and LLM applications. Proficient in Python, SQL, Java, and AWS. Builds scalable, production-ready solutions across NLP, computer vision, and data engineering.

---

## WORK EXPERIENCE BULLET VARIANTS

---

### CeADAR – Data Scientist Intern (May 2025 – Present)

**Current Default (Generic v2 — used in build_cv.py)**
*Role line: Data Scientist Intern*
- Designed and deployed a Retrieval-Augmented Generation (RAG) pipeline using LangChain, OpenAI, and Qdrant to enable domain-specific knowledge retrieval from PDFs and rice/agriculture websites
- Built a Streamlit and React based chatbot UI with memory, citations, and multilingual (English & Vietnamese) support, collaborating closely with cross-functional teams
- Automated PDF/web ingestion pipelines with chunking, embeddings (OpenAI/Qwen), metadata enrichment, and Qdrant storage, and implemented evaluation workflows using RAGAS to validate retrieval accuracy
- Developed a computer vision model using PyTorch to classify and label multiple rice disease varieties from field images, applying CNN-based architectures and transfer learning for early crop disease detection

**RiceAI Project bullets (used in PROJ_RICEAI in build_cv.py — tightened to avoid widow words)**
- Designed a full-stack RAG assistant for rice farming, integrating agricultural PDFs and web content with hybrid retrieval using LangChain and Qdrant
- Extended to GraphRAG (LangGraph + Neo4j) for explainable, knowledge-graph-enhanced retrieval with source traceability
- Delivered multilingual support (English & Vietnamese), automated ingestion pipelines, and RAGAS-validated quality benchmarking

**Generic / Full Bullets (v1)**
- Built and deployed a production-grade RAG pipeline using LangChain, OpenAI, and Qdrant, enabling accurate domain-specific knowledge retrieval from agricultural PDFs and live web sources with multilingual (English & Vietnamese) support
- Developed an end-to-end data ingestion pipeline covering PDF/web scraping, text chunking, embedding generation (OpenAI/Qwen), metadata enrichment, and vector storage in Qdrant and Supabase
- Implemented RAGAS-based evaluation workflows (BLEU, ROUGE, BERTScore) to benchmark and validate retrieval accuracy and generation quality across diverse query types
- Built a Streamlit and React chatbot UI with persistent memory and source citations, delivering a clean user experience for domain expert users
- Designed and trained a CNN-based computer vision model using PyTorch and transfer learning to classify multiple rice disease variants from field images, supporting early crop disease detection

**Condensed / 1-page bullets**
- Built a production-grade RAG pipeline (LangChain, OpenAI, Qdrant) for domain-specific agricultural knowledge retrieval with multilingual (English/Vietnamese) support and RAGAS-validated quality benchmarking
- Automated end-to-end data ingestion (PDF/web scraping, chunking, embeddings, Qdrant/Supabase storage) and developed a Streamlit/React chatbot UI with persistent memory and source citations
- Trained a CNN-based computer vision model (PyTorch, transfer learning) for rice disease classification from field images

**AI/LLM-focused variant**
- Architected a production RAG system using LangChain, OpenAI, and Qdrant; implemented hybrid retrieval with GraphRAG (LangGraph + Neo4j) for knowledge-graph-enhanced explainability
- Applied prompt engineering, embedding fine-tuning (OpenAI/Qwen), and RAGAS evaluation (BLEU, ROUGE, BERTScore) to iteratively improve retrieval accuracy and response quality
- Automated multi-source ingestion pipelines (PDFs + web) with chunking, metadata enrichment, and vector indexing at scale; shipped multilingual chatbot UI with React + Streamlit

**Computer Vision / Research variant**
- Designed and trained a CNN (PyTorch, transfer learning) to classify rice disease variants from unstructured field images, enabling early detection for sustainable agriculture
- Built evaluation and experiment tracking pipelines for CV model benchmarking; integrated with broader AI assistant ecosystem at CeADAR

**Analytics / BI variant**
- Delivered end-to-end data pipelines (ingestion → embeddings → vector store) from raw agricultural PDFs and web content, enabling structured knowledge retrieval for domain experts
- Implemented RAGAS evaluation dashboards to track retrieval quality metrics (BLEU, ROUGE, BERTScore) over model iterations, supporting data-driven improvements to the AI system

---

### LTIMindtree – Software Engineer, Data & AI / Citibank Client (Jun 2024 – Aug 2024)

**Current Default (Generic v2 — used in build_cv.py)**
*Role line: Software Engineer – SQL, Java & AI Projects (Citibank Client)*
- Optimized Oracle SQL queries and backend pipelines, improving data retrieval performance for Citibank's reporting systems
- Developed Java modules for intelligent data validation and integrated backend checks with early-stage anomaly detection logic
- Explored prompt engineering and Python-based model testing to support internal AI-assisted decision modules
- Designed and validated ML pipelines with quality checks and logging on AWS (Lambda + S3), ensuring data integrity and anomaly detection in low-latency environments

**Generic / Full (v1)**
- Optimized Oracle SQL queries and backend data pipelines for Citibank's reporting systems, improving data retrieval performance and reliability
- Developed Java modules for automated data validation and integrated anomaly detection logic into backend processing workflows
- Designed and deployed ML data quality pipelines on AWS (Lambda, S3) with structured logging, anomaly detection checks, and low-latency processing guarantees

**Condensed / 1-page**
- Optimized Oracle SQL queries and backend pipelines for Citibank's reporting systems; built Java data validation modules with anomaly detection
- Designed ML data quality pipelines on AWS (Lambda, S3) with logging, anomaly checks, and low-latency processing

**Data Engineering / Analytics variant**
- Tuned Oracle SQL reporting queries and ETL pipelines for Citibank, reducing query latency and improving downstream report reliability
- Built structured data validation and anomaly detection workflows in Java and AWS (Lambda, S3), ensuring data integrity across financial reporting pipelines

**AI / Software Engineering variant**
- Integrated early-stage anomaly detection and AI-assisted decision logic into Java backend modules for Citibank's data processing workflows
- Explored Python-based ML model testing and prompt engineering approaches to support internal AI-assisted decision modules

---

### Cognizant Technology Solutions – Programmer Analyst Trainee / Kohl's Corp (Dec 2023 – May 2024)

**Current Default (Generic v2 — used in build_cv.py)**
*Role line: Programmer Analyst Trainee – Kohl's Corp, US*
- Built conversational AI chatbot using Google Dialogflow, trained on CRM use cases to automate customer query prediction
- Developed backend services using Java and Spring Boot to integrate chatbot intelligence with CRM workflows
- Improved dynamic routing and response accuracy using Avaya Aura and Genesys Cloud with integrated AI triggers
- Designed intent classification strategies using NLP preprocessing and training phrase optimization, improving chatbot prediction accuracy by 18% across varied customer input

**Generic / Full (v1)**
- Built and deployed a conversational AI chatbot using Google Dialogflow for CRM-integrated automated customer query resolution
- Developed Java and Spring Boot backend services to connect chatbot intelligence with CRM workflows and dynamic call routing via Avaya Aura and Genesys Cloud
- Improved chatbot prediction accuracy by 18% through NLP-based intent classification redesign, training phrase optimization, and systematic preprocessing of customer input patterns

**Condensed / 1-page**
- Built a Dialogflow-based conversational AI chatbot integrated with CRM workflows via Java/Spring Boot and Avaya Aura/Genesys Cloud
- Improved chatbot prediction accuracy by 18% through NLP intent redesign and training phrase optimization

**NLP / AI variant**
- Designed and improved NLP intent classification for a production Dialogflow chatbot, achieving 18% accuracy lift through training phrase restructuring and preprocessing pipeline changes
- Integrated AI chatbot with CRM backend systems via Java/Spring Boot APIs, enabling end-to-end automated customer support routing

**Software / Backend variant**
- Developed Java and Spring Boot microservices integrating Google Dialogflow chatbot with CRM and call routing platforms (Avaya Aura, Genesys Cloud)
- Delivered backend data flow for automated customer query handling, reducing manual intervention in the support pipeline

---

## PROJECT VARIANTS

---

### RiceAI Expert – Sustainable Farming AI Chatbot (CeADAR, 2025)
*LangChain, LangGraph, Qdrant, OpenAI/Qwen, Streamlit, Supabase, Neo4j, RAGAS*

**Full / 2-page**
- Designed a full-stack RAG-based AI assistant for rice farming, integrating PDF and web content with hybrid retrieval using LangChain and Qdrant
- Extended architecture to GraphRAG (LangGraph + Neo4j) for explainable, knowledge-graph-enhanced retrieval with source traceability
- Delivered multilingual support (English & Vietnamese), automated ingestion pipelines, and RAGAS-validated response quality benchmarking

**Condensed / 1-page**
Full-stack RAG assistant for rice farming with GraphRAG (LangGraph + Neo4j), multilingual support, and RAGAS-benchmarked retrieval quality.

**AI/LLM-focused**
- Implemented hybrid RAG + GraphRAG system combining vector retrieval (Qdrant) with knowledge graph traversal (Neo4j/LangGraph) for explainable AI responses
- Evaluated retrieval quality with RAGAS (BLEU, ROUGE, BERTScore) across multilingual query sets; iterated on embeddings and chunking strategies to improve scores

---

### ScholarGenie – LLM Research Discovery Agent (March 2024)
*Python, LangChain, OpenAI GPT-4, arXiv API, Semantic Scholar API, Streamlit*

**Full / 2-page**
- Built an LLM-powered academic discovery tool integrating arXiv and Semantic Scholar APIs for real-time paper search, keyword filtering, and GPT-4-generated plain-language summaries
- Deployed with Streamlit for interactive exploration of AI-generated research summaries and trend analysis

**Condensed / 1-page**
LLM-powered paper discovery tool integrating arXiv and Semantic Scholar APIs with GPT-4 summaries and Streamlit interface.

---

### Face Verification – Siamese CNN (Research Paper, June 2023)
*TensorFlow, Keras, Python, NumPy, OpenCV*

**Full / 2-page**
- Developed a Siamese CNN for one-shot face verification, achieving 91.25% accuracy classifying 13,000 unique facial images; outperformed KNN and random-guess baselines
- Applied data augmentation, TensorBoard experiment tracking, and modular evaluation pipelines to ensure reproducibility and deployment readiness

**Role:** Data Collection and Preprocessing Lead, Model Development Support

**Condensed / 1-page**
Achieved 91.25% accuracy on 13,000 facial images using one-shot Siamese CNN; outperformed KNN baseline.

---

### Diabetes Health Outcome Dashboard using AWS (December 2024)
*AWS Redshift, AWS QuickSight, AWS S3, SQL, Python*
**Best for:** Cloud, Data Engineering, Analytics, BI, Full-Stack Data roles

**Full / 2-page**
- Developed a cloud-based data warehouse on AWS Redshift to analyze diabetes prevalence across demographic factors, integrating raw data via S3-based ingestion pipelines
- Built interactive dashboards in AWS QuickSight (bar charts, heatmaps) enabling real-time exploration of at-risk demographic patterns to support targeted public health interventions
- Designed a seamless end-to-end pipeline (S3 → Redshift → QuickSight) enabling real-time analytics and actionable insights on diabetes prevalence

**Condensed / 1-page**
Cloud BI dashboard on AWS (S3, Redshift, QuickSight) analyzing diabetes prevalence across demographics; delivered real-time insights via heatmaps and bar charts to support public health targeting.

**Cloud / Architecture-focused variant**
- Architected a serverless analytics stack on AWS: S3 for raw data storage, Redshift as cloud data warehouse, and QuickSight for business intelligence layer — fully integrated end-to-end
- Wrote SQL transformation logic in Redshift and Python preprocessing scripts to clean and model health outcome data before dashboard rendering

---

## SKILLS BANK

### Full Skills Table (2-page, table format)

| Category | Technologies |
|---|---|
| **Languages** | Python, SQL, Java, R, Bash |
| **ML & AI** | TensorFlow, PyTorch, scikit-learn, LangChain, OpenAI API, Hugging Face, Prompt Engineering, NLP, Computer Vision |
| **Data Engineering** | Apache Airflow, Apache Spark, Kafka, Pandas, NumPy, ETL Pipelines, AWS Glue |
| **Databases** | PostgreSQL, MySQL, MongoDB, Redis, AWS Redshift, AWS RDS |
| **Cloud & MLOps** | AWS (SageMaker, Lambda, S3, EC2, RDS), Azure ML, Docker, Kubernetes, MLflow |
| **Visualization** | Power BI, Matplotlib, Seaborn, Plotly, ggplot2 |
| **Tools & Frameworks** | Flask, FastAPI, Streamlit, Spring Boot, REST APIs, Git, OpenCV |

### Inline / Compact Skills (1-page format)
**Languages:** Python, SQL, Java, R, Bash | **ML/AI:** TensorFlow, PyTorch, scikit-learn, LangChain, OpenAI API, NLP, Computer Vision
**Data Engineering:** Airflow, Spark, Kafka, Pandas, ETL, AWS Glue | **Databases:** PostgreSQL, MySQL, MongoDB, AWS Redshift
**Cloud & MLOps:** AWS (SageMaker, Lambda, S3, EC2), Azure ML, Docker, Kubernetes, MLflow
**Visualization:** Power BI, Matplotlib, Seaborn, Plotly | **Tools:** Streamlit, Flask, FastAPI, Spring Boot, Git, OpenCV

### Analytics / BI-Focused Subset
Python, SQL, R, Power BI, Tableau, Pandas, NumPy, Excel, Matplotlib, Seaborn, Plotly, ggplot2, PostgreSQL, MySQL, AWS Redshift, AWS S3, Git

### Software Engineering Subset
Java, Python, SQL, Spring Boot, Flask, FastAPI, REST APIs, PostgreSQL, MySQL, MongoDB, AWS (Lambda, S3, EC2, RDS), Docker, Git

### AI/LLM-Focused Subset
Python, LangChain, LangGraph, OpenAI API, Hugging Face, Prompt Engineering, RAG, Vector Databases (Qdrant, FAISS), RAGAS, TensorFlow, PyTorch, NLP, Streamlit, AWS

---

## KEYWORDS BY JOB FAMILY

### Data Scientist / ML Engineer
machine learning, deep learning, NLP, computer vision, Python, scikit-learn, TensorFlow, PyTorch, model deployment, MLflow, feature engineering, data pipeline, ETL, AWS SageMaker, statistical modelling, experiment tracking, A/B testing, RAGAS, RAG, LLM, vector database

### Data Analyst / Business Intelligence
SQL, Python, Power BI, Tableau, data visualization, ETL, data wrangling, stakeholder reporting, dashboard, KPI, trend analysis, data quality, PostgreSQL, AWS Redshift, Excel, pandas

### AI / LLM Engineer
LLM, RAG, LangChain, LangGraph, prompt engineering, OpenAI, Hugging Face, embeddings, vector store, Qdrant, FAISS, RAGAS, chatbot, generative AI, knowledge graph, Neo4j, fine-tuning, evaluation, Streamlit, production AI

### Software Engineer (Backend / Data)
Java, Python, SQL, Spring Boot, REST APIs, microservices, data validation, anomaly detection, AWS Lambda, S3, ETL, PostgreSQL, Docker, Kubernetes, Git, CI/CD

### Research / NLP
NLP, intent classification, text classification, Transformers, BERT, GPT, embeddings, information retrieval, RAG, LangChain, evaluation metrics (BLEU, ROUGE, BERTScore), data augmentation, TensorFlow, PyTorch

---

## EDUCATION (Standard Block — reuse as-is)

**MSc Computer Science** | University College Dublin, Ireland | Sept 2024 – Sept 2025
First Class Honours (1:1)
*Key Modules: Cloud Computing, Multi-Agent Systems, Distributed Systems, Big Data Programming, Generative AI, RDBMS, Machine Learning, Enterprise & Innovation*

**BE Computer Science with Honours in AI-ML** | Savitribai Phule Pune University, India | Aug 2019 – May 2023
First Class Honours | CGPA: 8.97/10
*Key Modules: Object-Oriented Programming, Cloud Computing, Blockchain, AI-ML, Web Technologies*

---

## CERTIFICATIONS (Standard Block — reuse as-is)

- **AWS Certified Cloud Practitioner** | Dec 2024
- **Oracle Database SQL – 1Z0-071** | Aug 2024
- **Data Science – University of Michigan** | Dec 2023
- **AWS Academy Cloud Architecting** | May 2022
- **Linux Fundamentals** | Mar 2022

**Inline / compact format:**
AWS Certified Cloud Practitioner (2024) | Oracle SQL 1Z0-071 (2024) | Data Science – Univ. of Michigan (2023) | AWS Academy Cloud Architecting (2022)

---

## EXTRACURRICULAR (Keep brief or omit on 1-page)

- **Simon Community (Eaton Volunteering):** Volunteered in plantation and gardening drives, contributing to community welfare and environmental care
- **Badminton:** Represented school and college at national level; team captain
- **NSS (National Service Scheme):** Led community drives including blood donation camps
- **Microsoft Space AI Event:** Participated with Team CeADAR in frontier AI industry event

---

## TAILORING WORKFLOW (Quick Reference)

1. Get JD → identify role type (DS, ML, SWE, Analytics, AI/LLM, Research)
2. Pick matching headline from **Title Variants**
3. Pick matching summary from **Summary Variants**
4. Swap in matching experience bullets from **Experience Variants** (most impactful first)
5. Select skills subset from **Skills Bank** matching JD keywords
6. Pick 2–3 projects relevant to role type
7. Add JD-specific keywords naturally into bullets where truthful
8. Rename file: `SHANTANU_CV_<COMPANY_SHORT>.md`
9. Never modify master template files

---

*Last updated: March 2026*
