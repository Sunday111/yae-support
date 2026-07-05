#include <benchmark/benchmark.h>

#include <random>
#include <vector>

#include "EverydayTools/Bitset/BitIterator.hpp"
#include "EverydayTools/Bitset/BitsetAdapter.hpp"

static void BM_ForEach(benchmark::State& state)
{
    constexpr unsigned kSeed = 0;
    std::mt19937 generator(kSeed);  // NOLINT
    std::uniform_int_distribution<uint64_t> value_distribution;

    std::vector<size_t> actual;
    for (auto _ : state)
    {
        for (size_t i = 0; i != 10'000; ++i)
        {
            const auto bitset = value_distribution(generator);
            edt::BitsetAdapter adapter(bitset);
            actual.clear();

            adapter.ForEachBit(
                [&](const size_t bit_index)
                {
                    actual.push_back(bit_index);
                });
        }
    }
}

static void BM_Iterator(benchmark::State& state)
{
    constexpr unsigned kSeed = 0;
    std::mt19937 generator(kSeed);  // NOLINT
    std::uniform_int_distribution<uint64_t> value_distribution;

    std::vector<size_t> actual;

    for (auto _ : state)
    {
        for (size_t i = 0; i != 10'000; ++i)
        {
            const auto bitset = value_distribution(generator);
            edt::BitsetAdapter adapter(bitset);
            actual.clear();

            edt::BitIterator iterator(bitset);
            while (auto opt = iterator.Next())
            {
                actual.push_back(*opt);
            }

            benchmark::DoNotOptimize(actual);
        }
    }
}

BENCHMARK(BM_ForEach);
BENCHMARK(BM_Iterator);
