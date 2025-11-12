import streamlit as st
from pathlib import Path
from sqlalchemy import create_engine
import sqlite3
import re
import pandas as pd
import ast
from langchain.sql_database import SQLDatabase
from langchain_groq import ChatGroq
from langchain_experimental.sql import SQLDatabaseChain  # ✅ For LangChain ≥0.2

# ---------------------- Streamlit Config ----------------------
st.set_page_config(page_title="LangChain: Chat with SQL DB", page_icon=":robot_face:")
st.title("🤖 LangChain: Chat with SQL Database")

# ---------------------- Database Selection ----------------------
LOCALDB = "USE_LOCALDB"
MYSQL = "USE_MYSQL"

radio_opt = ["Use SQLite 3 Database - student.db", "Connect to your MySQL Database"]
selected_opt = st.sidebar.radio(label="Choose Database", options=radio_opt)

if radio_opt.index(selected_opt) == 1:
    db_uri = MYSQL
    mysql_host = st.sidebar.text_input("MySQL Host")
    mysql_user = st.sidebar.text_input("MySQL User")
    mysql_password = st.sidebar.text_input("MySQL Password", type="password")
    mysql_db = st.sidebar.text_input("MySQL Database Name")
else:
    db_uri = LOCALDB

api_key = st.sidebar.text_input(label="Groq API Key", type="password")

# ---------------------- Database Configuration ----------------------
@st.cache_resource(ttl="2h")
def configure_db(db_uri, mysql_host=None, mysql_user=None, mysql_password=None, mysql_db=None):
    """Creates a SQLDatabase connection object."""
    if db_uri == LOCALDB:
        dbfilepath = (Path(__file__).parent / "student.db").absolute()
        creator = lambda: sqlite3.connect(f"file:{dbfilepath}?mode=ro", uri=True)
        return SQLDatabase(create_engine("sqlite:///", creator=creator))
    elif db_uri == MYSQL:
        if not (mysql_host and mysql_user and mysql_password and mysql_db):
            st.error("Please provide all MySQL connection details.")
            st.stop()
        connection_uri = f"mysql+mysqlconnector://{mysql_user}:{mysql_password}@{mysql_host}/{mysql_db}"
        return SQLDatabase(create_engine(connection_uri))

# ---------------------- Connect to the Database ----------------------
if db_uri == MYSQL:
    if api_key and not (mysql_host and mysql_user and mysql_password and mysql_db):
        st.error("Please provide all MySQL connection details.")
        st.stop()
    db = configure_db(db_uri, mysql_host, mysql_user, mysql_password, mysql_db)
else:
    db = configure_db(db_uri)

# Show available tables in sidebar
try:
    tables = db.get_usable_table_names()
    st.sidebar.write("📋 Tables in DB:", tables if tables else "No tables found.")
except Exception as e:
    st.sidebar.error(f"Error fetching tables: {e}")

# ---------------------- Check for API Key ----------------------
if not api_key:
    st.info("🔑 Please add your Groq API key in the sidebar to start.")
    st.stop()

# ---------------------- Initialize LLM ----------------------
llm = ChatGroq(
    groq_api_key=api_key,
    model="llama-3.1-8b-instant",  # ✅ Stable Groq model
    streaming=False
)

# ---------------------- Create SQL Chain ----------------------
agent = SQLDatabaseChain.from_llm(
    llm=llm,
    db=db,
    verbose=True
)

# ---------------------- Utility: Clean SQL ----------------------
def clean_sql_query(raw_sql: str) -> str:
    """Cleans LLM-generated SQL strings from markdown and explanations."""
    # Remove code fences
    cleaned = re.sub(r"```sql|```", "", raw_sql, flags=re.IGNORECASE)
    # Remove commentary like "Let's run this query..." or trailing text
    cleaned = cleaned.split("Let's run")[0]
    # Remove trailing phrases or punctuation
    cleaned = cleaned.strip().strip(";")
    # Ensure single semicolon at end
    if not cleaned.endswith(";"):
        cleaned += ";"
    return cleaned

# ---------------------- Chat Interface ----------------------
if "messages" not in st.session_state or st.sidebar.button("🧹 Clear Chat History"):
    st.session_state["messages"] = [{"role": "assistant", "content": "Hello! Ask me anything about your database."}]

# Display previous chat
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# User input box
user_query = st.chat_input(placeholder="Type your SQL-related question here...")

# ---------------------- Handle User Query ----------------------
if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    st.chat_message("user").write(user_query)

    # Create a 2-column layout
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🧠 Model Reasoning & SQL Query")
    with col2:
        st.subheader("📊 Query Results")

    with st.chat_message("assistant"):
        try:
            # Run query through the SQL chain
            result = agent.invoke({"query": user_query})

            # Try extracting SQLQuery from the LLM response
            sql_query = None
            sql_match = re.search(r"SQLQuery:\s*(.*)", result["result"], re.IGNORECASE)
            if sql_match:
                sql_query = sql_match.group(1).strip()

            # Show reasoning + SQL query
            with col1:
                st.write(result["result"])
                if sql_query:
                    st.code(sql_query, language="sql")

            # ✅ Handle invalid or unclean SQL
            if sql_query:
                fixed_query = sql_query.strip()

                # Handle .schema/.tables replacements
                if fixed_query.startswith(".schema"):
                    fixed_query = "SELECT sql FROM sqlite_master WHERE type='table';"
                elif fixed_query.startswith(".tables"):
                    fixed_query = "SELECT name FROM sqlite_master WHERE type='table';"

                # Clean stray markdown or commentary
                fixed_query = clean_sql_query(fixed_query)

                # ✅ Execute safely and display results as DataFrame
                try:
                    query_result = db.run(fixed_query)

                    with col2:
                        try:
                            # Case 1: actual list
                            if isinstance(query_result, list):
                                data_list = query_result
                            # Case 2: string representation of list
                            elif isinstance(query_result, str) and query_result.startswith("[("):
                                data_list = ast.literal_eval(query_result)
                            else:
                                data_list = None

                            # Convert to DataFrame
                            if data_list:
                                # Try to detect column names dynamically
                                try:
                                    with db._engine.connect() as conn:
                                        result_proxy = conn.execute(fixed_query)
                                        columns = result_proxy.keys()
                                except Exception:
                                    columns = [f"col_{i+1}" for i in range(len(data_list[0]))] if data_list else []

                                df = pd.DataFrame(data_list, columns=columns)
                                st.dataframe(df)

                                # 📥 Add download button
                                csv_data = df.to_csv(index=False).encode("utf-8")
                                st.download_button(
                                    label="📥 Download Results as CSV",
                                    data=csv_data,
                                    file_name="query_results.csv",
                                    mime="text/csv"
                                )
                            else:
                                st.write(query_result)

                        except Exception as display_err:
                            st.warning(f"⚠️ Could not display table: {display_err}")

                except Exception as inner_err:
                    with col2:
                        st.warning(f"⚠️ Couldn't execute query: {inner_err}")

            # Save assistant message
            st.session_state.messages.append({"role": "assistant", "content": result["result"]})

        except Exception as e:
            st.error(f"⚠️ Error: {e}")
