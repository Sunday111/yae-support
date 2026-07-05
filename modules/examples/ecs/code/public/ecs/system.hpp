#pragma once

namespace ecs
{

class App;

class System
{
public:
    virtual void Tick(App& app) = 0;
    virtual void Initialize(App&){};
    virtual ~System() = default;
};

}  // namespace ecs
