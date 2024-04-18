from openai import OpenAI
from json import loads, dumps
from pathlib import Path
import os
from scipy.special import comb
from random import randint
from math import sqrt
rootpath = Path(__file__).parent

openaiClient = OpenAI()
def gpt_3_5_turbo_completion(query):
    answer = openaiClient.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": query
            }
        ],
        seed = randint(0, 1000000)
    )
    return answer.choices[0].message.content

def gpt_4_turbo_completion(query):
    answer = openaiClient.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {
                "role": "system",
                "content": query
            }
        ],
        seed = randint(0, 1000000)
    )
    return answer.choices[0].message.content

blabladorClient = OpenAI(base_url="https://helmholtz-blablador.fz-juelich.de:8000/v1/", api_key=os.environ["BLABLADOR_API_KEY"])
def mistral_7b_instruct_v_0_2_array_completion(query):
    answer = blabladorClient.completions.create(model="1 - Mistral-7B-Instruct-v0.2 - the best option in general - fast and good", 
                                                prompt=f"USER: {query} SYSTEM: ", 
                                                max_tokens=500,
                                                seed = randint(0, 1000000),
                                                temperature = 1).choices[0].text
    try:
        loadedArray = loads(answer)
        assert isinstance(loadedArray, list)
        for item in loadedArray:
            assert isinstance(item, str)
        return answer
    except:
        return gpt_3_5_turbo_completion('Extract the topic list from the following text. Return nothing but the list in the format ["topic1", "topic2", ...]: ' + answer)
def cosmoSage_json_array_completion(query):
    answer = blabladorClient.completions.create(model="4 - CosmoSage answers your cosmology questions", 
                                                prompt=f"USER: {query} SYSTEM: ", 
                                                max_tokens=500,
                                                seed = randint(0, 1000000)).choices[0].text
    try:
        loadedArray = loads(answer)
        assert isinstance(loadedArray, list)
        for item in loadedArray:
            assert isinstance(item, str)
        return answer
    except:
        return gpt_3_5_turbo_completion('If the following text containes a list of topics return it formated as ["topic1", "topic2", ...]. If it does not contain a list return "-". The text is : ' + answer)

def create_subtopic_tree_search_data():
    with (rootpath / "technical_terms.txt").open("r") as f:
        technical_terms = f.read().split("\n")
    subtopic_tree_search_file = rootpath / "subtopic_tree_search_data.txt"
    if subtopic_tree_search_file.exists():
        print("The file subtopic_tree_search_data.txt already exists.")
        return
    # Search data format: [[keyword, searchpath, subtopicspath, found, failed]]
    with subtopic_tree_search_file.open("w") as f:
        f.write("[\n")
        for keywordnr, keyword in enumerate(technical_terms):
            found = False
            failed = False
            searchpath = ["Physics"]
            subtopicspath = []
            while not found and not failed and len(searchpath) < 10:
                failed = True
                for i in range(10):
                    query = f'What are the subtopics of topic "{searchpath[-1]}" that together cover the entire range of the topic area? Return nothing but the list of subtopics formatted as: ["subtopic1", "subtopic2", ...]'
                    answer = gpt_3_5_turbo_completion(query)
                    try:
                        subtopics = loads(answer)
                        assert isinstance(subtopics, list)
                        for subtopic in subtopics:
                            assert isinstance(subtopic, str)
                        failed = False
                        break
                    except:
                        pass
                if failed:
                    print("Failed due to no subtopics found")
                    break
                subtopicspath.append(subtopics)
                failed = True
                for i in range(10):
                    subtopicSelection = "{" + ", ".join([f'{i} : "{x}"' for i, x in enumerate(subtopics)]) + "}"
                    query = f'Which of the following topics {subtopicSelection} is most likely to contain the keyword "{keyword}"? Return only the number without description.'
                    answer = gpt_3_5_turbo_completion(query)
                    try:
                        subtopicIndex = int(answer)
                        assert 0 <= subtopicIndex < len(subtopics)
                        chosenSubtopic = subtopics[subtopicIndex]
                        failed = False
                        break
                    except:
                        pass
                if failed:
                    print("Failed due to no subtopic chosen")
                    break
                searchpath.append(chosenSubtopic)
                if keyword.lower() in chosenSubtopic.lower():
                    found = True
            f.write("    " + dumps([keyword, found, failed, searchpath, subtopicspath]) + (",\n" if keywordnr < len(technical_terms) - 1 else "\n]"))
            f.flush()

def calculate_statistics():
    with (rootpath / "subtopic_tree_search_data.txt").open("r") as f:
        search_data = loads(f.read())
    totalfound = 0
    totalfailed = 0
    foundIterationsSum = 0
    totalSubtopics = 0
    totalSearchedTopics = 0
    alreadySearchedResults = dict()
    totalStabilityTests = 0
    stabelResults = 0
    for keyword, found, failed, searchpath, subtopicspath in search_data:
        if found:
            totalfound += 1
            foundIterationsSum += len(searchpath) - 1
        if failed:
            totalfailed += 1
        for subtopics in subtopicspath:
            totalSearchedTopics += 1
            totalSubtopics += len(subtopics)
        if not keyword in alreadySearchedResults:
            alreadySearchedResults[keyword] = found
        else:
            totalStabilityTests += 1
            if alreadySearchedResults[keyword] == found:
                stabelResults += 1
    foundPropability = totalfound / len(search_data)
    foundPercentage = 100 * foundPropability
    foundIterationsAverage = foundIterationsSum / totalfound if totalfound > 0 else None
    subtopicsPerSearchedTopic = totalSubtopics / totalSearchedTopics
    stabelPropability = stabelResults / totalStabilityTests if totalStabilityTests > 0 else None
    stabelResultsPercentage = 100 * stabelPropability if stabelPropability is not None else None
    # Calculate the found percentage error (See https://de.wikipedia.org/wiki/Binomialverteilung#M%C3%BCnzwurf)
    foundVariance = 0
    for k in range(1, len(search_data) + 1):
        foundVariance += ((k - totalfound) ** 2) * comb(len(search_data), k, exact = True) * (foundPropability ** k) * ((1 - foundPropability) ** (len(search_data) - k))
    foundError = sqrt(foundVariance) / len(search_data)
    foundPercentageError = 100 * foundError
    # Calculate the average number of iterations error (See https://www3.physik.uni-stuttgart.de/studium/praktika/ep/pdf_dateien/Allgemeines/Fehlerrechnung.pdf)
    foundIterationsVariance = 0
    for keyword, found, failed, searchpath, subtopicspath in search_data:
        if found:
            foundIterationsVariance += ((len(searchpath) - 1 - foundIterationsAverage) ** 2)
    foundIterationsError = sqrt(foundIterationsVariance / (totalfound - 1) / totalfound) if totalfound > 1 else None
    # Calculate the average number of subtopics per searched topic error
    subtopicsPerSearchedTopicVariance = 0
    for keyword, found, failed, searchpath, subtopicspath in search_data:
        for subtopics in subtopicspath:
            subtopicsPerSearchedTopicVariance += ((len(subtopics) - subtopicsPerSearchedTopic) ** 2)
    subtopicsPerSearchedTopicError = sqrt(subtopicsPerSearchedTopicVariance / (totalSearchedTopics - 1) / totalSearchedTopics) if totalSearchedTopics > 1 else None
    # Calculate the stability percentage error (See https://de.wikipedia.org/wiki/Binomialverteilung#M%C3%BCnzwurf)
    stabelVariance = 0
    for k in range(1, totalStabilityTests + 1):
        stabelVariance += ((k - stabelResults) ** 2) * comb(totalStabilityTests, k, exact = True) * (stabelPropability ** k) * ((1 - stabelPropability) ** (totalStabilityTests - k))
    stabelError = sqrt(stabelVariance) / totalStabilityTests if totalStabilityTests > 0 else None
    stabelResultsPercentageError = 100 * stabelError if stabelError is not None else None
    # Print the statistics
    print(f"""
        Total: {len(search_data)}, Found: {totalfound}, Failed: {totalfailed},
        FoundPercentage: {foundPercentage}%, FoundPercentageError: {foundPercentageError}%, 
        FoundIterationsAverage: {foundIterationsAverage}, FoundIterationsError: {foundIterationsError},
        AverageSubtopicsPerSearchedTopic: {subtopicsPerSearchedTopic}, SubtopicsPerSearchedTopicError: {subtopicsPerSearchedTopicError},
        StabelResultsPercentage: {stabelResultsPercentage}%, StabelResultsPercentageError: {stabelResultsPercentageError}%
        """)

create_subtopic_tree_search_data()
calculate_statistics()