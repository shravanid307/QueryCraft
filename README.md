# QueryCraft 
### A Multi-Agent Natural Language Query and Statistical Analysis System

QueryCraft is an AI-powered data analysis application that allows users to ask questions about structured datasets using natural language. It uses a multi-agent workflow to interpret questions, execute database queries, validate results, and perform statistical correlation analysis.

Built with Python, LangGraph, Groq, SQLite, and Streamlit, QueryCraft combines natural language processing with structured query execution and statistical analysis in a single interface.

##  Features

### 1. Natural Language to SQL
- Ask questions about structured data using natural language.
- Generate structured query plans using an LLM.
- Convert validated plans into SQL queries.
- Execute queries against SQLite databases.
- Display query results and generated SQL.

### 2. Multi-Agent Workflow
QueryCraft separates responsibilities across specialized workflow components:

- **Planner:** Interprets the user's question and creates a structured query plan.
- **Executor:** Builds and executes SQL queries while applying safety restrictions.
- **Critic:** Evaluates execution results and determines whether the answer is satisfactory or requires another attempt.
- **Retry Workflow:** Sends eligible failures back through the planning process for correction.

LangGraph orchestrates the workflow and its conditional transitions.

### 3. Statistical Correlation Analysis
QueryCraft also supports correlation analysis for numerical variables.

- Automatically identifies correlation-related questions.
- Selects suitable numerical columns from the database.
- Supports Pearson and Spearman correlation methods.
- Calculates the correlation coefficient and p-value.
- Reports correlation direction and approximate strength.
- Displays the number of valid and excluded observations.
- Validates statistical results through a Statistical Critic step.

**Important:** Correlation describes an association between variables and does not establish causation.

### 4. Data Upload
- Upload CSV and Excel (`.xlsx`) datasets.
- Preview datasets before importing them.
- View row counts, column counts, data types, and missing-value counts.
- Store uploaded datasets in independent SQLite databases.
- Query uploaded datasets through the application.

### 5. Interactive Streamlit Interface
- Select a database.
- Ask questions in natural language.
- View SQL query results in a table.
- Inspect generated SQL and query plans.
- View correlation statistics and their interpretation.
- Review the Critic's assessment.

### 6. Safety and Validation
The project includes SQL execution safeguards, structured plan validation, error handling, and tests for query safety and workflow recovery.

##  Architecture

QueryCraft supports two analysis paths.

### SQL Query Workflow

```text
User Question
     |
     v
Analysis Method Router
     |
     v
    Planner
     |
     v
   Executor
     |
     v
    Critic
     |
     +------ Approved ------> Final Result
     |
     +------ Retry ---------> Retry Planner
                                  |
                                  v
                               Planner
```

### Correlation Analysis Workflow

```text
User Question
     |
     v
Analysis Method Router
     |
     v
Correlation Column Selection
     |
     v
Statistical Analysis
     |
     v
Statistical Critic
     |
     v
Final Correlation Result
```

The application displays the results from the selected workflow through Streamlit.

##  Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application logic |
| LangGraph | Workflow orchestration |
| LangChain Groq | LLM integration |
| Groq | Language model inference |
| Pydantic | Structured data validation |
| SQLite | Database storage and SQL execution |
| Pandas | Data processing |
| SciPy | Statistical calculations |
| Streamlit | Interactive web interface |

##  Project Structure

```text
QueryCraft/
│
├── agents/
│   ├── schema_extractor.py
│   ├── planner.py
│   ├── executor.py
│   ├── critic.py
│   ├── graph.py
│   └── statistical_analysis.py
│
├── data/
│   └── ecommerce.db
│
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
│
└── test_*.py
```

*The structure above illustrates the main project components. Include the actual modules and tests present in your repository.*

##  Installation and Setup

### Prerequisites

- Python installed on your system.
- A Groq API key.
- Git, if cloning the repository.

### 1. Clone the Repository

```bash
git clone https://github.com/shravanid307/QueryCraft.git
cd QueryCraft
```

### 2. Create a Virtual Environment

On Windows:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a file named `.env` in the project root directory.

Add your own Groq API key:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
```

Replace the placeholder with your actual API key.

**Security:** Never commit your `.env` file or publish your API key. Keep `.env` excluded through `.gitignore`.

### 5. Run the Application

```bash
python -m streamlit run app.py
```

Streamlit will provide a local URL where you can access the application in your browser.

##  How to Use

### Ask Questions About Data

1. Open QueryCraft.
2. Select the database you want to query.
3. Enter a question in natural language.
4. Click **Run Query**.
5. Review the results, generated SQL, query plan, and Critic assessment.

Example questions for the sample e-commerce database:

- How many customers are in the database?
- What are the top five products by price?
- How many orders are there?
- Which suppliers are associated with the products?

The exact questions supported depend on the database schema and the query planner's capabilities.

### Perform Correlation Analysis

1. Open **Add Data**.
2. Upload a suitable CSV or Excel dataset.
3. Import the dataset.
4. Return to **Ask Questions** and select the uploaded database.
5. Ask a question about the relationship between two numerical variables.

Example:

> What is the correlation between alcohol and quality?

The result includes the correlation coefficient, method, p-value, correlation strength, direction, and observation counts.

##  Testing

The repository includes tests for components such as:

- Query planning
- SQL execution
- SQL safety
- Critic decisions and routing
- Workflow recovery and retry limits
- Statistical analysis
- Correlation column selection

Run the test suite with:

```bash
python -m pytest
```

Install `pytest` separately if it is not already available in your environment.

##  Limitations

- Query accuracy depends on the language model, database schema, and wording of the question.
- Correlation analysis requires suitable numerical variables and sufficient valid observations.
- Statistical significance does not imply practical importance or causation.
- The system's supported query operations depend on the planner and executor implementation.
- Uploaded datasets are stored locally in SQLite databases; deployment requires appropriate data-handling and access controls.

##  Future Improvements

Potential future enhancements include:

- Additional statistical analysis methods.
- More comprehensive automated evaluation of generated answers.
- Improved handling of ambiguous questions.
- Enhanced visualization of query and statistical results.
- Expanded support for database types and analytical operations.

##  Author

**Shravani Dixit**

GitHub: [@shravanid307](https://github.com/shravanid307)

##  License

A license has not yet been specified. Add a `LICENSE` file before distributing the project under an open-source license.
