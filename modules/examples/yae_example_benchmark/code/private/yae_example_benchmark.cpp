#include <benchmark/benchmark.h>

#include <random>
#include <vector>

static std::vector<uint32_t> MakeRandomVector()
{
    std::mt19937 gen(0);  // NOLINT
    constexpr size_t n = 100000;
    std::vector<uint32_t> values;
    values.reserve(n);
    std::uniform_int_distribution<uint32_t> distr;
    for (size_t i = 0; i != n; ++i)
    {
        values.push_back(distr(gen));
    }

    return values;
}

static void BM_VectorWithReserve(benchmark::State& state)
{
    const auto values = MakeRandomVector();

    // Perform setup here
    for (auto _ : state)
    {
        std::vector<uint32_t> copy;
        copy.reserve(values.size());
        for (const auto value : values)
        {
            copy.emplace_back(value);
            benchmark::DoNotOptimize(copy);
        }

        benchmark::DoNotOptimize(copy);
    }
}

static void BM_VectorWithoutReserve(benchmark::State& state)
{
    const auto values = MakeRandomVector();

    // Perform setup here
    for (auto _ : state)
    {
        std::vector<uint32_t> copy;
        for (const auto value : values)
        {
            copy.emplace_back(value);  // NOLINT
            benchmark::DoNotOptimize(copy);
        }
        benchmark::DoNotOptimize(copy);
    }
}

BENCHMARK(BM_VectorWithReserve);
BENCHMARK(BM_VectorWithoutReserve);

// Run the benchmark
BENCHMARK_MAIN();  // NOLINT
