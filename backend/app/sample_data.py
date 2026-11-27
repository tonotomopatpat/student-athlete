"""Built-in SAMPLE subjects so the system is usable before real content is loaded.

These are placeholders written for demonstration. Replace them with the real
general-education bank via `python -m app.cli import-questions FILE.csv`.
Each question is (text, choices, correct_index, explanation). The first three
questions of every topic are used as that topic's starting (diagnostic) quiz.
"""

Question = tuple[str, list[str], int, str]

SAMPLE_SUBJECTS: list[dict] = [
    {
        "code": "SAMPLE-MMW",
        "name": "Mathematics in the Modern World (sample)",
        "description": "Sample general-education subject: patterns, sets and basic statistics.",
        "topics": [
            {
                "name": "Patterns and Sequences",
                "questions": [
                    ("What is the next term in the sequence 2, 4, 6, 8, ...?", ["9", "10", "11", "12"], 1, "The sequence adds 2 each time, so 8 + 2 = 10."),
                    ("What is the next term in the Fibonacci sequence 1, 1, 2, 3, 5, 8, ...?", ["11", "12", "13", "14"], 2, "Each term is the sum of the two before it: 5 + 8 = 13."),
                    ("What is the common ratio of the geometric sequence 3, 6, 12, 24?", ["2", "3", "4", "6"], 0, "Each term is multiplied by 2: 6 / 3 = 2."),
                    ("An arithmetic sequence starts at 5 and has a common difference of 3. What is the 10th term?", ["30", "35", "32", "38"], 2, "a10 = 5 + 9 x 3 = 32."),
                    ("Which of these sequences is geometric?", ["2, 4, 6, 8", "5, 10, 15, 20", "10, 7, 4, 1", "1, 3, 9, 27"], 3, "Each term is multiplied by 3, so the ratio is constant."),
                    ("What is the sum of the first 5 positive integers?", ["10", "15", "20", "25"], 1, "1 + 2 + 3 + 4 + 5 = 15."),
                    ("What is the next term in 1, 4, 9, 16, ...?", ["20", "24", "36", "25"], 3, "These are perfect squares: 1, 2, 3, 4 squared, so the next is 5 squared = 25."),
                    ("What is the common difference of 17, 13, 9, 5?", ["4", "-3", "-4", "3"], 2, "Each term is 4 less than the one before: 13 - 17 = -4."),
                ],
            },
            {
                "name": "Sets and Venn Diagrams",
                "questions": [
                    ("If A = {1, 2, 3, 4} and B = {3, 4, 5, 6}, what is A \u2229 B?", ["{3, 4}", "{1, 2}", "{5, 6}", "{1, 2, 3, 4, 5, 6}"], 0, "The intersection contains elements in both sets: 3 and 4."),
                    ("If A = {1, 2, 3, 4} and B = {3, 4, 5, 6}, what is A \u222a B?", ["{3, 4}", "{1, 2, 5, 6}", "{1, 2, 3, 4, 5, 6}", "{1, 2, 3, 4}"], 2, "The union contains every element that is in A or B, without repeats."),
                    ("How many subsets does a set with 3 elements have?", ["6", "8", "9", "3"], 1, "A set with n elements has 2^n subsets, so 2^3 = 8."),
                    ("If A = {1, 2, 3, 4} and B = {3, 4, 5, 6}, what is A - B?", ["{3, 4}", "{5, 6}", "{1, 2, 5, 6}", "{1, 2}"], 3, "A - B is the elements of A that are not in B."),
                    ("Which symbol represents the empty set?", ["\u2205", "U", "\u2208", "\u2282"], 0, "\u2205 (or { }) is the set with no elements."),
                    ("If |A| = 10, |B| = 8 and |A \u2229 B| = 3, what is |A \u222a B|?", ["18", "21", "15", "11"], 2, "|A \u222a B| = 10 + 8 - 3 = 15."),
                    ("Let U = {1, 2, ..., 10} and A be the even numbers in U. What is the complement of A?", ["{2, 4, 6, 8, 10}", "{1, 3, 5, 7, 9}", "{1, 2, 3, 4, 5}", "{6, 7, 8, 9, 10}"], 1, "The complement holds the elements of U that are not in A: the odd numbers."),
                    ("Which set is a subset of {a, b, c}?", ["{a, d}", "{c, d}", "{b, c}", "{e}"], 2, "Every element of {b, c} is in {a, b, c}."),
                ],
            },
            {
                "name": "Basic Statistics",
                "questions": [
                    ("What is the mean of 2, 4, 6, 8, 10?", ["5", "6", "7", "8"], 1, "Sum = 30, and 30 / 5 = 6."),
                    ("What is the median of 3, 9, 5, 1, 7?", ["5", "3", "7", "9"], 0, "Sorted: 1, 3, 5, 7, 9. The middle value is 5."),
                    ("What is the mode of 2, 3, 3, 4, 5, 3, 6?", ["2", "4", "6", "3"], 3, "3 appears most often (three times)."),
                    ("What is the median of 4, 8, 6, 10?", ["6", "8", "7", "7.5"], 2, "Sorted: 4, 6, 8, 10. The two middle values average to (6 + 8) / 2 = 7."),
                    ("What is the range of 12, 5, 20, 9?", ["15", "8", "11", "20"], 0, "Range = largest - smallest = 20 - 5 = 15."),
                    ("Which measure of central tendency is most affected by an extreme outlier?", ["Median", "Mean", "Mode", "They are all affected equally"], 1, "The mean uses every value, so one extreme value shifts it the most."),
                    ("A data set in which two values tie for the most frequent is called:", ["unimodal", "trimodal", "bimodal", "amodal"], 2, "Two modes means bimodal."),
                    ("The mean of 5 numbers is 8. What is their sum?", ["13", "40", "8", "45"], 1, "Sum = mean x count = 8 x 5 = 40."),
                ],
            },
        ],
    },
    {
        "code": "SAMPLE-PC",
        "name": "Purposive Communication (sample)",
        "description": "Sample general-education subject: the communication process, grammar and academic writing.",
        "topics": [
            {
                "name": "The Communication Process",
                "questions": [
                    ("In the communication process, who creates and sends the message?", ["Receiver", "Sender", "Channel", "Noise"], 1, "The sender originates the message."),
                    ("The receiver's response to a message is called:", ["Feedback", "Noise", "Encoding", "Channel"], 0, "Feedback tells the sender how the message was received."),
                    ("Anything that interferes with a message being understood is called:", ["Channel", "Feedback", "Encoding", "Noise"], 3, "Noise can be physical, psychological or technical."),
                    ("The medium through which a message travels (such as speech, email or a call) is the:", ["Channel", "Sender", "Noise", "Feedback"], 0, "The channel carries the message from sender to receiver."),
                    ("The process of turning thoughts into words or symbols is called:", ["Decoding", "Encoding", "Feedback", "Noise"], 1, "Encoding is how the sender puts ideas into a message."),
                    ("What does decoding mean?", ["Creating the message", "Sending the message", "Blocking out noise", "Interpreting the message received"], 3, "The receiver decodes the message to understand it."),
                    ("A loud construction site disrupting a phone call is an example of:", ["Feedback", "Noise", "Encoding", "A channel"], 1, "It is external (physical) noise interfering with the message."),
                    ("Which situation best shows feedback?", ["A teacher emails the class", "A speaker prepares notes", "A listener nods and asks a clarifying question", "A projector stops working"], 2, "The listener is responding to the speaker."),
                ],
            },
            {
                "name": "Subject-Verb Agreement",
                "questions": [
                    ("Choose the correct verb: The athletes ___ late for practice.", ["was", "were", "is", "be"], 1, "'Athletes' is plural, so use 'were'."),
                    ("Choose the correct verb: Each of the players ___ a jersey.", ["have", "are having", "has", "were having"], 2, "'Each' is singular, so use 'has'."),
                    ("Choose the correct verb: Neither the coach nor the players ___ ready.", ["is", "are", "was", "has been"], 1, "With 'neither...nor', the verb agrees with the nearest subject: 'players' (plural)."),
                    ("Choose the correct verb: The list of requirements ___ long.", ["are", "is", "were", "have been"], 1, "The subject is 'list' (singular), not 'requirements'."),
                    ("Choose the correct verb: Mathematics ___ my favorite subject.", ["is", "are", "were", "have been"], 0, "'Mathematics' is a singular subject name."),
                    ("Choose the correct verb: My friends and I ___ going to the game.", ["am", "is", "are", "be"], 2, "A compound subject joined by 'and' is plural."),
                    ("Choose the correct verb: There ___ many reasons to study early.", ["is", "are", "was", "has"], 1, "The real subject, 'reasons', is plural."),
                    ("Choose the correct verb: Either the captain or the coaches ___ responsible.", ["is", "has been", "are", "was"], 2, "With 'either...or', the verb agrees with the nearest subject: 'coaches' (plural)."),
                ],
            },
            {
                "name": "Academic Writing Basics",
                "questions": [
                    ("What does a thesis statement do?", ["Lists all the sources used", "States the main argument of the essay", "Thanks the reader", "Defines every key term"], 1, "A thesis statement presents the central claim the essay supports."),
                    ("Plagiarism is:", ["Using someone else's work or ideas without credit", "Summarizing a source and citing it", "Quoting a source with a citation", "Writing in your own words"], 0, "Presenting others' work as your own, even unintentionally, is plagiarism."),
                    ("The sentence that presents the main idea of a paragraph is the:", ["Transition", "Conclusion", "Topic sentence", "Citation"], 2, "The topic sentence tells the reader what the paragraph is about."),
                    ("Which source is most reliable for academic research?", ["A peer-reviewed journal article", "An anonymous forum post", "A social media comment", "An advertisement"], 0, "Peer-reviewed articles are checked by experts before publication."),
                    ("Paraphrasing means:", ["Copying the exact words and adding quotation marks", "Ignoring the source", "Restating an idea in your own words and still crediting the source", "Translating the source into another language"], 2, "A paraphrase uses new wording but still needs a citation."),
                    ("An in-text citation is used to:", ["Fill the word count", "Replace the thesis statement", "Make the essay look longer", "Show where an idea or fact came from"], 3, "It links a statement in the text to its source."),
                    ("What is the usual order of an essay's structure?", ["Introduction, body, conclusion", "Body, introduction, conclusion", "Conclusion, body, introduction", "Body, conclusion, introduction"], 0, "An essay introduces the topic, develops it, then concludes."),
                    ("The main purpose of a conclusion is to:", ["Introduce a brand-new argument", "List more sources", "Wrap up the main points and leave a final takeaway", "Repeat the introduction word for word"], 2, "A conclusion summarizes and closes the argument."),
                ],
            },
        ],
    },
]
