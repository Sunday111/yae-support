#include "ecs/entity_collection.hpp"

namespace ecs::entity_collection_impl
{

void EntityPool::FreeEntity(EntityIndex entity_index)
{
    auto& entity = GetEntityInfo(entity_index);
    entity.Free();
    entity.next_free = first_free_;
    first_free_ = entity_index;
}

std::pair<EntityIndex, EntityInfo*> EntityPool::AllocEntity()
{
    auto [page_index, index_on_page] = DecomposeIndex(first_free_, false);
    assert(page_index < pages_.size() || (page_index == pages_.size() && index_on_page == 0));
    if (page_index == pages_.size())
    {
        AddPage();
    }

    const EntityIndex entity_index = first_free_;
    std::tie(page_index, index_on_page) = DecomposeIndex(entity_index);
    EntityInfo& entity_info = pages_[page_index][index_on_page];
    first_free_ = entity_info.next_free;
    entity_info.Occupy();
    return {entity_index, &entity_info};
}

void EntityPool::AddPage()
{
    using EIdx = typename EntityId::Repr;
    const auto first_id = static_cast<EIdx>(pages_.size() * kEntityCollectionPageSize);

    auto& page = pages_.emplace_back();
    page.resize(kEntityCollectionPageSize);
    for (size_t index_on_page = 0; index_on_page != page.size(); ++index_on_page)
    {
        page[index_on_page].next_free = EntityIndex::FromValue(first_id + static_cast<EIdx>(index_on_page + 1));
    }

    first_free_ = EntityIndex::FromValue(first_id);
}
}  // namespace ecs::entity_collection_impl

namespace ecs
{

EntityId EntityCollection::CreateEntity()
{
    const auto entity_id = GenerateId();
    const auto [entity_index, entity_info] = entities_.AllocEntity();
    id_to_index_[entity_id] = entity_index;
    return entity_id;
}

void EntityCollection::DestroyEntity(const EntityId entity_id)
{
    assert(id_to_index_.contains(entity_id));
    entities_.FreeEntity(id_to_index_[entity_id]);
    id_to_index_.erase(entity_id);
}

EntityId EntityCollection::GenerateId()
{
    while (id_to_index_.contains(next_id_))
    {
        const auto invalid_id = EntityId{}.GetValue();
        next_id_ = EntityId::FromValue(static_cast<EntityId::Repr>((next_id_.GetValue() + 1) % invalid_id));
    }
    return next_id_;
}

EntityInfo& EntityCollection::GetEntityInfo(const EntityId entity_id)
{
    assert(id_to_index_.contains(entity_id));
    return entities_.GetEntityInfo(id_to_index_[entity_id]);
}

const EntityInfo& EntityCollection::GetEntityInfo(const EntityId entity_id) const
{
    auto idx_it = id_to_index_.find(entity_id);
    assert(idx_it != id_to_index_.end());
    return entities_.GetEntityInfo(idx_it->second);
}

}  // namespace ecs
