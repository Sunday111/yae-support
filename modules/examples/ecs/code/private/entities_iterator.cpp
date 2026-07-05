#include "ecs/entities_iterator.hpp"

namespace ecs
{
EntitiesIterator_ErasedType::EntitiesIterator_ErasedType(App& app, std::span<internal::ComponentPool*> pools)
    : pools_(pools),
      app_(&app)
{
    std::ranges::sort(pools_, std::less{}, &internal::ComponentPool::GetAllocatedCount);
    if (pools_.size() > 0)
    {
        smallest_pool_iterator_ = internal::ComponentPoolIterator(*pools_.front());
    }
}

std::optional<EntityId> EntitiesIterator_ErasedType::Next()
{
    if (smallest_pool_iterator_.has_value())
    {
        while (auto opt = smallest_pool_iterator_->Next())
        {
            const auto entity_id = *opt;
            bool has_all_components = true;
            for (size_t index = 1; index < pools_.size(); ++index)
            {
                auto pool = pools_[index];
                if (!app_->HasComponent(entity_id, pool->GetType()))
                {
                    has_all_components = false;
                    break;
                }
            }

            if (has_all_components)
            {
                return entity_id;
            }
        }
    }

    return std::nullopt;
}
}  // namespace ecs
