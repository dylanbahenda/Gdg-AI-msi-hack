from contracts.types import LLMInput
from modules.llm.interface import LLMReasoner

reasoner = LLMReasoner()

test_input = LLMInput(
    sound_class="baby_cry",
    sed_confidence=0.95,
    doa_direction_of_arrival=45.5,
    doa_distance_estimation=2.0,
)

result = reasoner.reason(test_input)
print(result)