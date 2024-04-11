from sqlite3 import connect
from openai import OpenAI
from json import loads

llmClient = OpenAI()
llmModel = "gpt-3.5-turbo"
llmSeed = 0
def chat(query, seed = llmSeed):
    answer = llmClient.chat.completions.create(
        model=llmModel,
        seed = seed,
        messages=[
            {
                "role": "system",
                "content": query
            }
        ]
    )
    return answer.choices[0].message.content

con = connect("subtopic-network-search.sqlite")
cur = con.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS topics (id INTEGER PRIMARY KEY, topic TEXT UNIQUE, subtopicsGenerated BOOLEAN)")
cur.execute("CREATE TABLE IF NOT EXISTS subtopics (id INTEGER PRIMARY KEY, topic_id INTEGER, subtopic_id INTEGER)")
cur.execute("CREATE TABLE IF NOT EXISTS keywordSearch (id INTEGER PRIMARY KEY, keyword TEXT UNIQUE, searchpath TEXT, found BOOLEAN, failed BOOLEAN)")
rootTopic = "physics"
cur.execute("INSERT OR IGNORE INTO topics (topic, subtopicsGenerated) VALUES (?, ?)", (rootTopic, False))
con.commit()

# Get the id of the root topic
cur.execute("SELECT id FROM topics WHERE topic=?", (rootTopic,))
rootTopicId = cur.fetchone()[0]

def getTopicFromId(topicId):
    cur.execute("SELECT topic FROM topics WHERE id=?", (topicId,))
    return cur.fetchone()[0]

def ensureSubtopics(topicId):
    """
    Ensure that the subtopics of a topic are generated
    """
    cur.execute("SELECT subtopicsGenerated FROM topics WHERE id=?", (topicId,))
    subtopicsGenerated = cur.fetchone()[0]
    if subtopicsGenerated:
        return
    cur.execute("SELECT topic FROM topics WHERE id=?", (topicId,))
    topic = cur.fetchone()[0]
    answer = chat(f'What are the subtopics of topic "{topic}" that together cover the entire range of the topic area? Return nothing but the list of subtopics formatted as json array: ["subtopic1", "subtopic2", ...]')
    try:
        subtopics = loads(answer)
        assert type(subtopics) == list
        for subtopic in subtopics:
            assert type(subtopic) == str
    except:
        print("Error: The answer is not a valid json array")
        return
    for subtopic in subtopics:
        subtopic = subtopic.strip().lower()
        cur.execute("INSERT OR IGNORE INTO topics (topic, subtopicsGenerated) VALUES (?, ?)", (subtopic, False))
        cur.execute("SELECT id FROM topics WHERE topic=?", (subtopic,))
        subtopicId = cur.fetchone()[0]
        cur.execute("INSERT OR IGNORE INTO subtopics (topic_id, subtopic_id) VALUES (?, ?)", (topicId, subtopicId))
    cur.execute("UPDATE topics SET subtopicsGenerated = 1 WHERE id=?", (topicId,))
    con.commit()

def searchKeyword(keyword, maxDepth=10):
    """
    Search for a keyword in the subtopic network
    Return a tupel (found keyword or None, failed)
    """
    cur.execute("INSERT OR IGNORE INTO keywordSearch (keyword, searchpath, found, failed) VALUES (?, ?, ?, ?)", (keyword, str(rootTopicId), False, False))
    cur.execute("SELECT searchpath, found, failed FROM keywordSearch WHERE keyword=?", (keyword,))
    con.commit()
    searchpath, found, failed = cur.fetchone()
    searchpath = [int(x) for x in searchpath.split(",")]
    # Check if the search is already completed
    if found:
        if len(searchpath) > maxDepth:
            return (None, False)
        return (getTopicFromId(searchpath[-1]), False)
    if failed:
        if len(searchpath) <= maxDepth:
            return (None, True)
        return (None, False)
    if len(searchpath) >= maxDepth:
        return (None, False)
    # Continue search
    while len(searchpath) < maxDepth:
        lastTopicId = searchpath[-1]
        ensureSubtopics(lastTopicId)
        cur.execute("SELECT subtopic_id FROM subtopics WHERE topic_id=?", (lastTopicId,))
        subtopics = cur.fetchall()
        subtopics = [x[0] for x in subtopics if not x[0] in searchpath]
        if len(subtopics) == 0:
            failed = True
            break
        subtopicNames = [getTopicFromId(x) for x in subtopics]
        subtopicNameSelection = "{" + ", ".join([f'{i} : "{x}"' for i, x in enumerate(subtopicNames)]) + "}"
        answer = chat(f'Which of the following topics {subtopicNameSelection} is most likely to contain the keyword "{keyword}"? Return only the number without description.')
        try:
            index = int(answer)
            assert 0 <= index < len(subtopics)
        except:
            failed = True
            break
        searchpath.append(subtopics[index])
        # Check if the keyword is equivalent to the chosen subtopic
        if  subtopicNames[index].lower() in keyword.lower():
            found = True
            break
    cur.execute("UPDATE keywordSearch SET searchpath=?, found=?, failed=? WHERE keyword=?", (",".join([str(x) for x in searchpath]), found, failed, keyword))
    con.commit()
    if found:
        return (subtopicNames[index], False)
    if failed:
        return (None, True)
    return (None, False)

def searchKeywordAndReturnPath(keyword, maxDepth=10):
    """
    Search for a keyword in the subtopic network
    """
    newKeyword, failed = searchKeyword(keyword, maxDepth)
    cur.execute("SELECT searchpath, found, failed FROM keywordSearch WHERE keyword=?", (keyword,))
    searchpath = cur.fetchone()[0]
    searchpath = [getTopicFromId(int(x)) for x in searchpath.split(",")]
    return (searchpath, newKeyword, failed)

def exportAllSearchPaths():
    """
    Export all search paths to a file
    """
    cur.execute("SELECT keyword, searchpath, found, failed FROM keywordSearch")
    with open("searchpaths.txt", "w") as file:
        for keyword, searchpath, found, failed in cur.fetchall():
            searchpath = [getTopicFromId(int(x)) for x in searchpath.split(",")]
            file.write(f"{keyword}: {searchpath}\n")

with open("technical_terms.txt", "r") as file:
    technicalTerms = file.read().split("\n")
for term in technicalTerms:
    searchKeyword(term, 10)
exportAllSearchPaths()
