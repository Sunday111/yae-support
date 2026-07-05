#pragma once

#include <cstddef>

#include "EverydayTools/Bitset/BitIterator.hpp"
#include "EverydayTools/Bitset/BitsetAdapter.hpp"
#include "EverydayTools/Bitset/BitsetUtilities.hpp"

namespace ecs::internal
{

template <typename Iterable>
class EntityHasComponentIterator;

template <size_t kCapacity, typename Part_>
struct EntityHasComponent
{
    using Part = Part_;
    static constexpr size_t kPartBitsCount = 8 * sizeof(Part);
    static constexpr size_t kPartsCount = kCapacity / kPartBitsCount;
    static_assert((kCapacity % kPartBitsCount) == 0, "No remainder allowed");
    using PartBitsType = edt::BitCountToTypeT<kPartsCount>;
    std::array<Part, kPartsCount> parts{};
    PartBitsType parts_bits = 0;

    constexpr void Set(const size_t index, const bool value) noexcept
    {
        const size_t part_index = index / kPartBitsCount;
        const size_t index_in_part = index % kPartBitsCount;
        auto& part = parts[part_index];
        const edt::BitsetAdapter part_adapter(part);
        assert(part_adapter.Get(index_in_part) != value);
        part_adapter.Set(index_in_part, value);
        if (value || part == 0)
        {
            const edt::BitsetAdapter parts_adapter(parts_bits);
            assert(value || parts_adapter.Get(part_index) != value);
            parts_adapter.Set(part_index, value);
        }
    }

    constexpr bool IsEmpty() const noexcept
    {
        return parts_bits == 0;
    }

    template <typename Callback>
    bool ForEachBit(Callback&& callback)
    {
        return edt::BitsetAdapter(parts_bits)
            .ForEachBitWithReturn(
                [&](const size_t part_index)
                {
                    const auto& part = parts[part_index];
                    if (part == 0) return true;
                    return edt::BitsetAdapter(part).ForEachBitWithReturn(
                        [&](const size_t bit_index)
                        {
                            const size_t index_on_page = part_index * kPartBitsCount + bit_index;
                            return callback(index_on_page);
                        });
                });
    }
};

template <typename Iterable>
class EntityHasComponentIterator
{
public:
    using PartsIteratorType = edt::BitIterator<typename Iterable::PartBitsType>;
    using PartIteratorType = edt::BitIterator<typename Iterable::Part>;

    explicit EntityHasComponentIterator(Iterable& iterable)
        : iterable_(&iterable),
          part_index_(0),
          part_iterator_(std::nullopt)
    {
        const edt::BitsetAdapter parts_adapter(iterable_->parts_bits);
        part_index_ = parts_adapter.NextBitAfter(0);
        if (part_index_ < parts_adapter.kBitsCount)
        {
            part_iterator_ = PartIteratorType(iterable_->parts[part_index_]);
        }
    }

    static size_t BitIndexToIndexOnPage(const size_t part_index, const size_t bit_index)
    {
        const size_t index_on_page = part_index * Iterable::kPartBitsCount + bit_index;
        return index_on_page;
    }

    std::optional<size_t> Next()
    {
        if (part_iterator_.has_value())
        {
            if (auto maybe_bit_index = part_iterator_->Next(); maybe_bit_index.has_value())
            {
                return BitIndexToIndexOnPage(part_index_, *maybe_bit_index);
            }

            part_iterator_ = std::nullopt;
        }
        else
        {
            const edt::BitsetAdapter parts_adapter(iterable_->parts_bits);
            part_index_ = parts_adapter.NextBitAfter(part_index_ + 1);
            if (part_index_ >= parts_adapter.kBitsCount)
            {
                return std::nullopt;
            }
            part_iterator_ = PartIteratorType(iterable_->parts[part_index_]);
        }

        return Next();
    }

private:
    Iterable* iterable_;
    size_t part_index_;
    std::optional<PartIteratorType> part_iterator_;
};

}  // namespace ecs::internal
