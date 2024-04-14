from sqlite3 import connect
from openai import OpenAI
from json import loads
import os

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
blabladorClient = OpenAI(base_url="https://helmholtz-blablador.fz-juelich.de:8000/v1/", api_key=os.environ["BLABLADOR_API_KEY"])
blabladorModel = "1 - Mistral-7B-Instruct-v0.2 the best option in general - fast and good"
def blablador(query, seed = llmSeed):
    answer = blabladorClient.completions.create(model=blabladorModel, prompt=f"USER: {query} SYSTEM: ", max_tokens=500, seed=seed)
    return answer.choices[0].text

subtopicNetworkCompletion = blablador
searchCompletion = chat

nameOfTheDataCollection = "mistral"

con = connect(f"{nameOfTheDataCollection}-evaluation.sqlite")
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
    tryNumber = 0
    maxTries = 10
    subtopicsLoaded = False
    while not subtopicsLoaded and tryNumber < maxTries:
        answer = subtopicNetworkCompletion(f'What are the subtopics of topic "{topic}" that together cover the entire range of the topic area? Return nothing but the list of subtopics formatted as json array: ["subtopic1", "subtopic2", ...]',
                                           seed = llmSeed + tryNumber)
        try:
            subtopics = loads(answer)
            assert type(subtopics) == list
            for subtopic in subtopics:
                assert type(subtopic) == str
            subtopicsLoaded = True
        except:
            pass
        tryNumber += 1
    if not subtopicsLoaded:
        print(f"Failed to load subtopics for topic {topic}")
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
        subtopicChosen = False
        maxTries = 10
        tryNumber = 0
        while not subtopicChosen and tryNumber < maxTries:
            answer = searchCompletion(f'Which of the following topics {subtopicNameSelection} is most likely to contain the keyword "{keyword}"? Return only the number without description.',
                                        seed = llmSeed + tryNumber)
            try:
                index = int(answer)
                assert 0 <= index < len(subtopics)
                subtopicChosen = True
            except:
                pass
            tryNumber += 1
        if not subtopicChosen:
            failed = True
            print(f"Failed to choose subtopic for keyword {keyword}")
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
    with open(f"{nameOfTheDataCollection}-searchpaths.txt", "w") as file:
        for keyword, searchpath, found, failed in cur.fetchall():
            searchpath = [getTopicFromId(int(x)) for x in searchpath.split(",")]
            file.write(f"{keyword}: {searchpath}\n")

def navigateSubtopicNetwork():
    """
    Navigate the subtopic network
    """
    currentTopicId = rootTopicId
    while True:
        print(f"{getTopicFromId(currentTopicId)} (id: {currentTopicId})")
        # Print all super topics
        cur.execute("SELECT topic_id FROM subtopics WHERE subtopic_id=?", (currentTopicId,))
        superTopics = cur.fetchall()
        superTopics = [x[0] for x in superTopics]
        superTopicNames = [getTopicFromId(x) + f" (id: {x})" for x in superTopics]
        superTopicNames.sort(key=lambda x: (x.lower(), x))
        print("Super topics:")
        for superTopic in superTopicNames:
            print("     " + superTopic)
        # Print all sub topics
        cur.execute("SELECT subtopic_id FROM subtopics WHERE topic_id=?", (currentTopicId,))
        subTopics = cur.fetchall()
        subTopics = [x[0] for x in subTopics]
        subTopicNames = [getTopicFromId(x) + f" (id: {x})" for x in subTopics]
        subTopicNames.sort(key=lambda x: (x.lower(), x))
        print("Sub topics:")
        for subTopic in subTopicNames:
            print("     " + subTopic)
        # Ask for the next topic
        nextTopic = input("Next topic id: ")
        if nextTopic == "":
            break
        try:
            nextTopic = int(nextTopic)
            # Test if the next topic id is in the database
            cur.execute("SELECT topic FROM topics WHERE id=?", (nextTopic,))
            topic = cur.fetchone()
            if topic:
                currentTopicId = nextTopic
            else:
                print("Invalid topic id")
        except:
            print("Invalid topic id")


with open("technical_terms.txt", "r") as file:
    technicalTerms = file.read().split("\n")
for term in technicalTerms:
    searchKeyword(term, 10)
exportAllSearchPaths()
navigateSubtopicNetwork()
