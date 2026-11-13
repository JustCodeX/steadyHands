"""Everything that needs the Cactus runtime (`cactus-compute`): the Needle
tool-calling model and the Whistle speech-to-text model.

Optional: the app runs without the package and without the model files, and
falls back to the keyword matcher, the keyword evaluator and Vosk. Nothing
outside this package imports `cactus`.
"""
