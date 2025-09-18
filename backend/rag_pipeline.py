from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate
from pinecone import Pinecone

from config import (
    OPENAI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_ENV,
    PINECONE_INDEX,
    EMBEDDING_MODEL,
)

# Init Pinecone (client)
pc = Pinecone(api_key=PINECONE_API_KEY)

embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
vectorstore = PineconeVectorStore(index_name=PINECONE_INDEX, embedding=embeddings)

# Base LLM (used by agents)
llm = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY, temperature=0)

def get_conversational_chain(session_id: str):
    retriever = vectorstore.as_retriever(
        search_kwargs={"filter": {"session_id": session_id}, "k": 5}
    )
    prompt = PromptTemplate(
        input_variables=["context", "chat_history", "question"],
        template="""
You are a helpful and intelligent research assistant. Use the following retrieved documents, along with the chat history between a user and an assistant, to answer the user's latest question. Always use the previous conversation for context, and answer follow-up questions accurately. If you don't know, say so honestly.

Retrieved documents:
{context}

Chat history:
{chat_history}

User's question:
{question}

Your answer:
"""
    )

    qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": prompt}
    )
    return qa_chain

def generate_overall_summary(topic: str, session_id: str, summaries: list):
    retriever = vectorstore.as_retriever(
        search_kwargs={"filter": {"session_id": session_id}, "k": 8}
    )
    relevant_docs = retriever.invoke(topic)

    prompt = PromptTemplate(
        input_variables=["topic", "summaries", "docs"],
        template="""
You are a careful research assistant. Based on the topic "{topic}", the per-article summaries below,
and the most relevant document chunks retrieved from the session and also your own knowledge, capabilities,
and sense, produce a thorough, structured research summary. Be factual, cite sources inline like [#], and
include a References section mapping [#] to title + URL.

Per-article summaries:
{summaries}

Retrieved chunks:
{docs}

Write a final research synthesis.
"""
    )
    final_input = prompt.format(
        topic=topic,
        summaries="\n\n".join([s.content if hasattr(s, 'content') else str(s) for s in summaries]),
        docs="\n\n".join([d.page_content for d in relevant_docs])
    )
    return llm.invoke(final_input)
