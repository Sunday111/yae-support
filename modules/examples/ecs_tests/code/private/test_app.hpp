#pragma once

#include "ecs/app.hpp"

class TestApp : public ecs::App
{
public:
    TestApp();
    ~TestApp() override;
    void RegisterReflectionTypes() override;
    void RegisterComponents() override;
    void CreateSystems() override;
};
