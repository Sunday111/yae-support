#include "ecs/internal/component_pool.hpp"

#include <bit>
#include <cassert>

#include "EverydayTools/Bitset/BitsetAdapter.hpp"
#include "EverydayTools/Bitset/BitsetArrayAdapter.hpp"

namespace ecs::internal
{

ComponentPoolIterator::ComponentPoolIterator(ComponentPool& pool) : pool_(&pool)
{
    page_index_ = 0;
    if (page_index_ < pool_->pages_.size())
    {
        page_iterator_ = EntityHasComponentIteratorType(pool_->pages_[page_index_].component_exists);
    }
}

std::optional<EntityId> ComponentPoolIterator::Next()
{
    if (page_iterator_.has_value())
    {
        if (auto maybe_index = page_iterator_->Next(); maybe_index.has_value())
        {
            auto& page = pool_->pages_[page_index_];
            return page.metadata[*maybe_index].entity_id;
        }

        page_iterator_ = std::nullopt;
    }
    else
    {
        if (++page_index_ >= pool_->pages_.size())
        {
            page_index_ = pool_->pages_.size();
            return std::nullopt;
        }
        page_iterator_ = EntityHasComponentIteratorType(pool_->pages_[page_index_].component_exists);
    }

    return Next();
}
}  // namespace ecs::internal

namespace ecs::internal
{
ComponentPool::ComponentPool(const cppreflection::Type* type) : type_(type)
{
    cell_size_ = std::max(type_->GetInstanceSize(), sizeof(EmptyCell));
    cell_alignment_ = std::max(type_->GetAlignment(), alignof(EmptyCell));
}

ComponentPool::CellIndex ComponentPool::Alloc(const EntityId entity_id)
{
    auto [page_index, index_on_page] = Decompose(first_free_);
    if (page_index >= pages_.size())
    {
        assert(page_index == pages_.size());
        AddPage();
    }

    const auto cell_index = first_free_;
    std::tie(page_index, index_on_page) = DecomposeChecked(cell_index);

    auto cell = GetFreeCell(page_index, index_on_page);
    first_free_ = cell->next;  // Remember next free
    type_->GetSpecialMembers().defaultConstructor(cell);

    auto& page = pages_[page_index];
    page.metadata[index_on_page].entity_id = entity_id;
    page.component_exists.Set(index_on_page, true);
    used_count_++;

    return cell_index;
}

void ComponentPool::Free(const CellIndex cell_index)
{
    const auto [page_index, index_on_page] = DecomposeChecked(cell_index);
    auto cell = GetCellPtr(page_index, index_on_page);
    type_->GetSpecialMembers().destructor(cell);
    const auto empty_cell = reinterpret_cast<EmptyCell*>(cell);  // NOLINT
    empty_cell->next = first_free_;
    first_free_ = static_cast<CellIndex>(cell_index);

    auto& page = pages_[page_index];
    page.metadata[index_on_page].entity_id = EntityId{};
    page.component_exists.Set(index_on_page, false);
    --used_count_;
}

void ComponentPool::AddPage()
{
    assert(first_free_ == pages_.size() * kComponentPoolPageSize);
    const size_t bytes_count = cell_size_ * (kComponentPoolPageSize + 1);  // +1 for alignment

    const auto page_index = static_cast<CellIndex>(pages_.size());
    auto& page = pages_.emplace_back();
    page.data.reset(new uint8_t[bytes_count]);  // NOLINT

    size_t aligned_address = reinterpret_cast<size_t>(page.data.get());  // NOLINT
    if (const size_t remainder = aligned_address % cell_alignment_; remainder != 0)
    {
        aligned_address += cell_alignment_ - remainder;
    }

    page.aligned = reinterpret_cast<uint8_t*>(aligned_address);  // NOLINT

    auto next_free = first_free_;
    for (CellIndex index_on_page = 0; index_on_page != kComponentPoolPageSize; ++index_on_page)
    {
        GetFreeCell(page_index, index_on_page)->next = ++next_free;
    }
}

}  // namespace ecs::internal
