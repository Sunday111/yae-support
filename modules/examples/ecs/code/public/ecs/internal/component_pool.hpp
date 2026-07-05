#pragma once

#include <array>
#include <cassert>
#include <cstdint>
#include <memory>
#include <optional>
#include <vector>

#include "CppReflection/Type.hpp"
#include "EverydayTools/Bitset/BitIterator.hpp"
#include "ecs/constants.hpp"
#include "ecs/entity_id.hpp"
#include "entity_has_component.hpp"

namespace ecs::internal
{

class ComponentPool;
class ComponentPoolIterator;

class ComponentPool
{
public:
    friend ComponentPoolIterator;

    using CellIndex = uint32_t;
    using ForEachComponentCallbackRaw = bool (*)(void* user_data, const EntityId entity_id);
    using EntityHasComponentType = internal::EntityHasComponent<kComponentPoolPageSize, uint64_t>;

    struct ComponentMetadata
    {
        ecs::EntityId entity_id;
    };

private:
    struct Page
    {
        std::unique_ptr<uint8_t[]> data;  // NOLINT
        uint8_t* aligned = nullptr;
        std::array<ComponentMetadata, kComponentPoolPageSize> metadata;
        EntityHasComponentType component_exists;
    };

public:
    explicit ComponentPool(const cppreflection::Type*);

    CellIndex Alloc(const EntityId entity_id);
    void Free(const CellIndex cell_index);
    void* Get(const CellIndex cell_index)
    {
        const auto [page_index, index_on_page] = DecomposeChecked(cell_index);
        return GetCellPtr(page_index, index_on_page);
    }

    inline const cppreflection::Type* GetType() const noexcept
    {
        return type_;
    }

    inline size_t GetAllocatedCount() const noexcept
    {
        return used_count_;
    }

    template <typename Callback>
    bool ForEach(Callback&& callback);

private:
    struct EmptyCell
    {
        CellIndex next;
    };

private:
    template <bool checked>
    inline std::pair<uint32_t, uint32_t> DecomposeImpl(const CellIndex cell_index) const
    {
        const uint32_t page_index = cell_index / kComponentPoolPageSize;
        if constexpr (checked) assert(page_index < pages_.size());
        const uint32_t index_on_page = cell_index % kComponentPoolPageSize;
        return {page_index, index_on_page};
    }

    inline std::pair<uint32_t, uint32_t> DecomposeChecked(const CellIndex cell_index) const
    {
        return DecomposeImpl<true>(cell_index);
    }

    inline std::pair<uint32_t, uint32_t> Decompose(const CellIndex cell_index) const
    {
        return DecomposeImpl<false>(cell_index);
    }

    void* GetCellPtr(const uint32_t page_index, const uint32_t index_on_page)
    {
        auto& page = pages_[page_index];
        const auto cell = page.aligned + cell_size_ * index_on_page;  // NOLINT
        return cell;
    }

    EmptyCell* GetFreeCell(const uint32_t page_index, const uint32_t index_on_page)
    {
        const auto cell_raw = GetCellPtr(page_index, index_on_page);
        const auto cell = reinterpret_cast<EmptyCell*>(cell_raw);  // NOLINT
        return cell;
    }

    void AddPage();

private:
    const cppreflection::Type* type_ = nullptr;
    size_t cell_size_ = 0;
    size_t cell_alignment_ = 0;
    std::vector<Page> pages_;  // NOLINT
    size_t used_count_ = 0;
    CellIndex first_free_ = 0;
};
class ComponentPoolIterator
{
public:
    using EntityHasComponentType = typename ComponentPool::EntityHasComponentType;
    using EntityHasComponentIteratorType = EntityHasComponentIterator<EntityHasComponentType>;

    explicit ComponentPoolIterator(ComponentPool& pool);

    std::optional<EntityId> Next();
    static size_t ToIndex(const size_t page_index, const size_t index_on_page)
    {
        return page_index * kComponentPoolPageSize + index_on_page;
    }

    ComponentPool* pool_;
    size_t page_index_ = 0;
    std::optional<EntityHasComponentIteratorType> page_iterator_;
};

template <typename Callback>
bool ComponentPool::ForEach(Callback&& callback)
{
    ComponentPoolIterator iterator(*this);
    while (auto opt = iterator.Next())
    {
        if (!callback(*opt))
        {
            return false;
        }
    }

    return true;
}
}  // namespace ecs::internal
