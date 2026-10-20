# Building the C++ engine

This build has no Python opponent. The engine is required, so build it
before the first run:

    g++ -O2 -std=c++17 -o hexcharge_engine engine.cpp

On Windows with MinGW the output name should be `hexcharge_engine.exe`;
`AiCpp.py` looks for that automatically.

Put the binary next to `HexCharge.py`. If it is missing, the game says so
and exits rather than starting with a different opponent.

## After changing the rules

`engine.cpp` restates the rules in a second language, so it can drift
away from `Rules.py`. After ANY change to the rules, rebuild and run:

    python3 test_engine.py 400

It builds random positions and checks that both implementations produce
exactly the same list of legal actions. It has already caught one real
difference (promotion during legality testing), so it is worth the
thirty seconds it takes.
