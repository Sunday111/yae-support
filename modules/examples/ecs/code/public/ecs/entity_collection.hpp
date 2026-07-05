#pragma once

#include <cassert>
#include <cstddef>
#include <tuple>
#include <unordered_map>
#include <vector>

#include "CppReflection/Type.hpp"
#include "EverydayTools/Bitset/DynamicBitset.hpp"
#include "constants.hpp"
#include "entity_id.hpp"

namespace ecs
{
class EntityInfo
{
public:
    struct ComponentInfo
    {
        void* component = nullptr;
        uint32_t pool_index = 0;
    };

    void Free() {}
    void Occupy() {}

    EntityIndex next_free;
    ankerl::unordered_dense::map<const cppreflection::Type*, ComponentInfo> components;
};
}  // namespace ecs

namespace ecs::entity_collection_impl
{

class EntityPool
{
public:
    void FreeEntity(EntityIndex index);
    std::pair<EntityIndex, EntityInfo*> AllocEntity();

    EntityInfo& GetEntityInfo(const EntityIndex& entity_index)
    {
        const auto [page_index, index_on_page] = DecomposeIndex(entity_index);
        return pages_[page_index][index_on_page];
    }

    const EntityInfo& GetEntityInfo(const EntityIndex& entity_index) const
    {
        const auto [page_index, index_on_page] = DecomposeIndex(entity_index);
        return pages_[page_index][index_on_page];
    }

private:
    void AddPage();

private:
    std::pair<size_t, size_t> DecomposeIndex(
        const EntityIndex entity_index,
        [[maybe_unused]] const bool check_bounds = true) const noexcept
    {
        assert(entity_index.IsValid());
        const size_t page_index = static_cast<size_t>(entity_index.GetValue()) / kEntityCollectionPageSize;
        assert(page_index < pages_.size() || !check_bounds);
        const size_t index_on_page = static_cast<size_t>(entity_index.GetValue()) % kEntityCollectionPageSize;
        assert(index_on_page < kEntityCollectionPageSize || !check_bounds);
        return {page_index, index_on_page};
    }

private:
    using Page = std::vector<EntityInfo>;
    std::vector<Page> pages_;
    EntityIndex first_free_ = EntityIndex::FromValue(0);
};

}  // namespace ecs::entity_collection_impl

namespace ecs
{

class EntityCollection
{
public:
    EntityId CreateEntity();
    void DestroyEntity(const EntityId entity_id);
    EntityInfo& GetEntityInfo(const EntityId entity_id);
    const EntityInfo& GetEntityInfo(const EntityId entity_id) const;
    bool HasEntity(const EntityId entity_id) const
    {
        return id_to_index_.contains(entity_id);
    }

private:
    EntityId GenerateId();

private:
    ankerl::unordered_dense::map<EntityId, EntityIndex> id_to_index_;
    EntityId next_id_ = EntityId::FromValue(0);
    entity_collection_impl::EntityPool entities_;
};

}  // namespace ecs
