const SAMPLE_QUESTIONS: Record<string, string[]> = {
  "conv-30": [
    "How long did it take for Jon to open his studio?",
    "What is Jon's favorite style of dance?",
    "When is Jon's dance studio opening?",
  ],
  "conv-41": [
    "What are Maria's dogs' names?",
    "What martial arts has John done?",
    "Who did Maria have dinner with on May 3, 2023?",
  ],
  "conv-42": [
    "What are Joanna's hobbies?",
    "How long has Nate had his first two turtles?",
    "When did Nate get his first two turtles?",
  ],
  "conv-43": [
    "What items does John collect?",
    "What books has Tim read?",
    "What sports does John like besides basketball?",
  ],
  "conv-44": [
    "Which year did Audrey adopt the first three of her dogs?",
    "Did Andrew have a pet dog during March 2023?",
    "When did Andrew go rock climbing?",
  ],
  "conv-47": [
    "What are the names of James's dogs?",
    "Which recreational activity was James pursuing on March 16, 2022?",
    "Does James live in Connecticut?",
  ],
  "conv-48": [
    "Is Deborah married?",
    "Which country were Jolene and her mother visiting in 2010?",
    "What symbolic gifts do Deborah and Jolene have from their mothers?",
  ],
};

export function questionsForSample(sampleId: string): string[] {
  return SAMPLE_QUESTIONS[sampleId] ?? [];
}
